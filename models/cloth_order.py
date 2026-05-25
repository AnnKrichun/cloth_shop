# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClothOrder(models.Model):
    _name = "cloth.order"
    _description = "Customer Sales Order"
    _order = "date_order desc, id desc"

    name = fields.Char(
        string="Order Reference",
        required=True,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    phone = fields.Char(string="Phone")
    email = fields.Char(string="Email")
    date_order = fields.Datetime(
        string="Order Date", default=fields.Datetime.now, required=True
    )
    delivery_address = fields.Text(string="Delivery Address", required=True)

    line_ids = fields.One2many("cloth.order.line", "order_id", string="Order Lines")
    discount = fields.Float(string="Personal Discount (%)")
    amount_total = fields.Float(
        string="Total Amount", compute="_compute_amount_total", store=True
    )

    state = fields.Selection(
        [
            ("draft", "In Progress"),
            ("shipped", "Shipped"),
            ("received", "Received"),
            ("rejected", "Customer Return"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("cloth.order") or _(
                    "New"
                )
        return super().create(vals_list)

    @api.depends("line_ids", "discount")
    def _compute_amount_total(self):
        """Простий і надійний підрахунок загальної суми замовлення"""
        for order in self:
            subtotal = sum(
                line.price_subtotal for line in order.line_ids if line.price_subtotal
            )
            order.amount_total = subtotal * (1.0 - (order.discount / 100.0))

    def write(self, vals):
        """Контроль залишків при зміні статусів відвантаження"""
        for order in self:
            old_state = order.state
            new_state = vals.get("state", old_state)

            if old_state != new_state:
                if new_state == "shipped" and old_state == "draft":
                    order._update_stock()

        return super().write(vals)

    def action_state_shipped(self):
        self.write({"state": "shipped"})

    def action_state_received(self):
        self.write({"state": "received"})

    def action_state_rejected(self):
        self.write({"state": "rejected"})

    def action_state_cancelled(self):
        self.write({"state": "cancelled"})

    def _update_stock(self):
        """
        🛠️ NEW MATRIX VALIDATION: Performs strict inventory verification
        individually for each specific size layer via transient matrix metrics.
        """
        for line in self.line_ids:
            if line.product_id and line.size_id:
                # Initialize virtual stock line structure logic to extract size balance
                transient_stock_line = self.env["cloth.product.stock.line"].new(
                    {"product_id": line.product_id.id, "size_id": line.size_id.id}
                )
                transient_stock_line._compute_metrics()

                if transient_stock_line.qty_available < line.qty:
                    raise ValidationError(
                        _(
                            "Insufficient stock balance for product %s in Size %s! Available on hand: %s"
                        )
                        % (
                            line.product_id.name,
                            line.size_id.name,
                            transient_stock_line.qty_available,
                        )
                    )


class ClothOrderLine(models.Model):
    _name = "cloth.order.line"
    _description = "Sales Order Line"

    order_id = fields.Many2one("cloth.order", ondelete="cascade", string="Parent Order")
    product_id = fields.Many2one("cloth.product", string="Product", required=True)

    # 🛠️ NEW ARCHITECTURE SLOT: Manual size parameter row indicator link
    size_id = fields.Many2one("cloth.size", string="Size", required=True)

    qty = fields.Integer(string="Quantity", default=1, required=True)
    price_unit = fields.Float(string="Unit Price")
    price_subtotal = fields.Float(
        string="Subtotal", compute="_compute_price_subtotal", store=True
    )

    # 🛠️ UPDATED MATRIX PRICE TRIGGER: Evaluates rules anytime product OR target size updates
    @api.onchange("product_id", "size_id")
    def _onchange_product_id(self):
        """
        Dynamically scans verified goods receipt notes history to extract
        the latest calculated retail pricing tag for BOTH selected SKU and specific size.
        """
        if self.product_id and self.size_id:
            latest_receipt_line = self.env["cloth.receipt.line"].search(
                [
                    ("sku_id", "=", self.product_id.id),
                    (
                        "size_id",
                        "=",
                        self.size_id.id,
                    ),  # Strict sizing matching parameter
                    ("receipt_id.state", "=", "done"),
                ],
                order="id desc",
                limit=1,
            )

            if latest_receipt_line:
                self.price_unit = latest_receipt_line.retail_price
            else:
                self.price_unit = 0.00
        else:
            self.price_unit = 0.00

    @api.depends("qty", "price_unit")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
