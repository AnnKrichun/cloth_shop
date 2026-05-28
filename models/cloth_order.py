# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ClothOrder(models.Model):
    """
    Model for managing customer sales orders.
    Handles order sequences, statuses, and inventory stock availability validations.
    """

    _name = "cloth.order"
    _description = "Customer Sales Order"
    _order = "date_order desc, id desc"

    # Core order reference number generated automatically
    name = fields.Char(
        string="Order Reference",
        required=True,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    date_order = fields.Datetime(
        string="Order Date",
        default=fields.Datetime.now,
        required=True,
    )
    delivery_address = fields.Text(string="Delivery Address", required=True)

    # Relational field linking to order items lines
    line_ids = fields.One2many("cloth.order.line", "order_id", string="Order Lines")
    discount = fields.Float(string="Personal Discount (%)")

    # Calculated order financial matrix summary
    amount_total = fields.Float(
        string="Total Amount",
        compute="_compute_amount_total",
        store=True,
        digits=(12, 2),
    )

    # State machine configuration handling business statuses
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
        readonly=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Extends create method to assign unique transaction sequence codes.
        """
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                # COMMENT: Fetches next numeric code from ir_sequence_data.xml file
                vals["name"] = self.env["ir.sequence"].next_by_code("cloth.order") or _(
                    "New"
                )
        return super().create(vals_list)

    @api.depends("line_ids.price_subtotal", "discount")
    def _compute_amount_total(self):
        """
        Calculates the final order value with customer discount percentages deducted.
        """
        for order in self:
            subtotal = sum(
                line.price_subtotal for line in order.line_ids if line.price_subtotal
            )
            discount_val = order.discount or 0.00
            order.amount_total = subtotal * (1.0 - (discount_val / 100.0))

    def write(self, vals):
        """
        Extends write method to secure documents state locking and inventory triggers.
        """
        if "state" in vals and not self.env.context.get("install_demo"):
            for order in self:
                # COMMENT: Prevents users from modifying validated or cancelled order records
                if order.state in ["shipped", "received", "cancelled", "rejected"]:
                    raise ValidationError(
                        _(
                            "Operation not allowed! Order '%s' is already in a final state (%s) and cannot be moved."
                        )
                        % (order.name, order.state.upper()),
                    )

        res = super().write(vals)

        # COMMENT: Triggers automatic warehouse inventory deductions when order transitions to Shipped
        if "state" in vals:
            for order in self:
                if vals["state"] == "shipped":
                    order._update_stock()
        return res

    # Interface state changer methods triggered via views button headers
    def action_state_shipped(self):
        """Moves order to Shipped state."""
        self.write({"state": "shipped"})

    def action_state_received(self):
        """Moves order to Received state."""
        self.write({"state": "received"})

    def action_state_rejected(self):
        """Moves order to Rejected state."""
        self.write({"state": "rejected"})

    def action_state_cancelled(self):
        """Moves order to Cancelled state."""
        self.write({"state": "cancelled"})

    def _update_stock(self):
        """
        Validates real-time inventory balances before enabling document status mutations.
        """
        for line in self.line_ids:
            if line.product_id and line.size_id:
                # COMMENT: We generate a transient stock checker instance on the fly to count matrix pieces
                transient_stock_line = self.env["cloth.product.stock.line"].new(
                    {"product_id": line.product_id.id, "size_id": line.size_id.id},
                )
                transient_stock_line._compute_metrics()

                # COMMENT: Block validation loop if store balance cannot fulfill order specs
                if transient_stock_line.qty_available < line.qty:
                    raise ValidationError(
                        _(
                            "Insufficient stock balance for product [%s] %s in Size %s! Available on hand: %s"
                        )
                        % (
                            line.product_id.name,
                            line.product_id.product_title,
                            line.size_id.name,
                            transient_stock_line.qty_available,
                        ),
                    )

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        """
        Fetches client personal discount directly onto the active transaction layout.
        """
        for order in self:
            if order.partner_id:
                partner_data = self.env["res.partner"].search_read(
                    [("id", "=", order.partner_id.id)],
                    ["personal_discount"],
                )
                if partner_data and partner_data[0].get("personal_discount"):
                    order.discount = partner_data[0]["personal_discount"]
                else:
                    order.discount = 0.0
            else:
                order.discount = 0.0

    def action_recalculate_discount(self):
        """
        Recalculates total values and forces pricing matrix updates inside form layout.
        """
        for order in self:
            if order.partner_id:
                order.discount = order.partner_id.personal_discount or 0.0
                order._compute_amount_total()

                # COMMENT: Synchronize all lines values matching active vectors cascades
                for line in order.line_ids:
                    line._compute_price_unit()
                    line._compute_price_subtotal()


class ClothOrderLine(models.Model):
    """
    Model representing an individual item line inside a customer sales order.
    """

    _name = "cloth.order.line"
    _description = "Sales Order Line"

    order_id = fields.Many2one("cloth.order", ondelete="cascade", string="Parent Order")
    product_id = fields.Many2one("cloth.product", string="Product", required=True)
    size_id = fields.Many2one("cloth.size", string="Size", required=True)
    qty = fields.Integer(string="Quantity", default=1, required=True)

    # COMMENT: readonly=True locks the field from manual typing by the sales manager
    price_unit = fields.Float(
        string="Unit Price",
        compute="_compute_price_unit",
        store=True,
        readonly=True,
        digits=(12, 2),
    )

    price_subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_price_subtotal",
        store=True,
        digits=(12, 2),
    )

    @api.depends("product_id", "size_id")
    def _compute_price_unit(self):
        """
        Computes the unit retail price by searching the active retail price matrix.
        """
        for line in self:
            if line.product_id and line.size_id:
                # COMMENT: We search the pricing matrix table to find the correct retail price
                price_record = self.env["cloth.product.price"].search(
                    [
                        ("product_id", "=", line.product_id.id),
                        ("size_id", "=", line.size_id.id),
                    ],
                    limit=1,
                )
                if price_record:
                    line.price_unit = price_record.retail_price
                else:
                    line.price_unit = 0.00
            else:
                line.price_unit = 0.00

    @api.onchange("product_id", "size_id")
    def _onchange_product_size(self):
        """
        Updates the interface price instantly when a user changes the product or size.
        """
        if self.product_id and self.size_id:
            # COMMENT: Fetches the same matrix retail price for instant browser feedback
            price_record = self.env["cloth.product.price"].search(
                [
                    ("product_id", "=", self.product_id.id),
                    ("size_id", "=", self.size_id.id),
                ],
                limit=1,
            )
            self.price_unit = price_record.retail_price if price_record else 0.00

    @api.depends("qty", "price_unit")
    def _compute_price_subtotal(self):
        """
        Calculates the total line price before any order discounts are applied.
        """
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
