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
    date_order = fields.Datetime(
        string="Order Date", default=fields.Datetime.now, required=True
    )
    delivery_address = fields.Text(string="Delivery Address", required=True)

    line_ids = fields.One2many("cloth.order.line", "order_id", string="Order Lines")
    discount = fields.Float(string="Personal Discount (%)")

    amount_total = fields.Float(
        string="Total Amount",
        compute="_compute_amount_total",
        store=True,
        digits=(12, 2),
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
        readonly=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("cloth.order") or _(
                    "New"
                )
        return super().create(vals_list)

    @api.depends("line_ids.price_subtotal", "discount")
    def _compute_amount_total(self):
        """Простий і надійний підрахунок загальної суми замовлення"""
        for order in self:
            subtotal = sum(
                line.price_subtotal for line in order.line_ids if line.price_subtotal
            )
            discount_val = order.discount or 0.00
            order.amount_total = subtotal * (1.0 - (discount_val / 100.0))

    def write(self, vals):
        """Контроль залишків та блокування перетягування карток для закритих замовлень"""
        # 🔒 БЛОКУВАННЯ ПЕРЕТЯГУВАННЯ (Тільки для користувачів в UI, ігноруємо при завантаженні демо)
        if "state" in vals and not self.env.context.get("install_demo"):
            for order in self:
                if order.state in ["shipped", "received", "cancelled", "rejected"]:
                    raise ValidationError(
                        _(
                            "Operation not allowed! Order '%s' is already in a final state (%s) and cannot be moved."
                        )
                        % (order.name, order.state.upper())
                    )

        # Зберігаємо дані в базу
        res = super().write(vals)

        # Після збереження виконуємо контроль залишків для нових відвантажень
        if "state" in vals:
            for order in self:
                if vals["state"] == "shipped":
                    order._update_stock()
        return res

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
        🛠️ STRICT MATRIX VALIDATION: Performs inventory verification
        individually for each specific size layer via transient matrix metrics.
        """
        for line in self.line_ids:
            if line.product_id and line.size_id:
                # Ініціалізуємо віртуальну лінію для розрахунку залишку на льоту
                transient_stock_line = self.env["cloth.product.stock.line"].new(
                    {"product_id": line.product_id.id, "size_id": line.size_id.id}
                )
                transient_stock_line._compute_metrics()

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
                        )
                    )

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        """Пряме вичитування знижки з бази даних в обхід веб-кешу Odoo"""
        for order in self:
            if order.partner_id:
                # 🔒 Прямий запит до БД: читаємо значення поля personal_discount прямо з таблиці res_partner
                partner_data = self.env["res.partner"].search_read(
                    [("id", "=", order.partner_id.id)], ["personal_discount"]
                )
                if partner_data and partner_data[0].get("personal_discount"):
                    order.discount = partner_data[0]["personal_discount"]
                else:
                    order.discount = 0.0
            else:
                order.discount = 0.0

    def action_recalculate_discount(self):
        """Кнопка для примусового перерахунку знижки та суми в існуючому замовленні"""
        for order in self:
            if order.partner_id:
                # 1. Беремо актуальну знижку з картки клієнта
                order.discount = order.partner_id.personal_discount or 0.0

                # 2. Примусово викликаємо метод підрахунку суми замовлення
                order._compute_amount_total()

                # 3. Додатково оновлюємо суми рядків, якщо це необхідно (про всяк випадок)
                for line in order.line_ids:
                    line._compute_price_unit()
                    line._compute_price_subtotal()


class ClothOrderLine(models.Model):
    _name = "cloth.order.line"
    _description = "Sales Order Line"

    order_id = fields.Many2one("cloth.order", ondelete="cascade", string="Parent Order")
    product_id = fields.Many2one("cloth.product", string="Product", required=True)
    size_id = fields.Many2one("cloth.size", string="Size", required=True)
    qty = fields.Integer(string="Quantity", default=1, required=True)

    # 🔒 ФІКС: Поле суворо readonly=True. Менеджер не зможе його змінити вручну.
    price_unit = fields.Float(
        string="Unit Price",
        compute="_compute_price_unit",
        store=True,
        readonly=True,  # Перекриваємо доступ на рівні ORM
        digits=(12, 2),
    )

    price_subtotal = fields.Float(
        string="Subtotal", compute="_compute_price_subtotal", store=True, digits=(12, 2)
    )

    # 🛠️ Обчислювальний метод, який працює і для бази, і для інтерфейсу
    @api.depends("product_id", "size_id")
    def _compute_price_unit(self):
        for line in self:
            if line.product_id and line.size_id:
                # Шукаємо останню ціну в проведених надходженнях
                latest_receipt_line = self.env["cloth.receipt.line"].search(
                    [
                        ("sku_id", "=", line.product_id.id),
                        ("size_id", "=", line.size_id.id),
                        ("receipt_id.state", "=", "done"),
                    ],
                    order="id desc",
                    limit=1,
                )
                if latest_receipt_line:
                    line.price_unit = latest_receipt_line.retail_price
                else:
                    line.price_unit = 0.00
            else:
                line.price_unit = 0.00

    # ⚡ ДОДАТКОВИЙ ТРИГЕР: Для моментального відгуку інтерфейсу в браузері
    @api.onchange("product_id", "size_id")
    def _onchange_product_size(self):
        """Змушує вебинтерфейс моментально показати ціну при виборі товару/розміру"""
        if self.product_id and self.size_id:
            latest_receipt_line = self.env["cloth.receipt.line"].search(
                [
                    ("sku_id", "=", self.product_id.id),
                    ("size_id", "=", self.size_id.id),
                    ("receipt_id.state", "=", "done"),
                ],
                order="id desc",
                limit=1,
            )
            self.price_unit = (
                latest_receipt_line.retail_price if latest_receipt_line else 0.00
            )

    @api.depends("qty", "price_unit")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
