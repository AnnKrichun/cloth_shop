# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClothReceipt(models.Model):
    """Model managing stock intake operations and incoming supplier shipments."""

    _name = "cloth.receipt"
    _description = "Goods Receipt Note"
    _order = "date desc, id desc"

    name = fields.Char(
        string="Document Number",
        required=True,
        readonly=True,
        default=lambda self: _("New"),
    )
    date = fields.Date(string="Date", default=fields.Date.context_today, required=True)
    line_ids = fields.One2many(
        "cloth.receipt.line", "receipt_id", string="Product Lines"
    )
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Validated")],
        string="Status",
        default="draft",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "cloth.receipt"
                ) or _("New")
        return super().create(vals_list)

    def action_calculate_retail_prices(self):
        """Calculates final store consumer tags using advanced multi-currency conversion paths."""
        stored_param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cloth_shop.retail_currency_id")
        )
        retail_currency = (
            self.env["res.currency"].browse(int(stored_param))
            if stored_param and stored_param.isdigit()
            else self.env.company.currency_id
        )

        for line in self.line_ids:
            if line.sku_id and line.brand_id and line.collection_id:
                rule = self.env["cloth.markup.coefficient"].search(
                    [
                        ("brand_id", "=", line.brand_id.id),
                        ("collection_id", "=", line.collection_id.id),
                    ],
                    limit=1,
                )
                coef = rule.coefficient if rule else 1.0
                purchase_currency = (
                    line.purchase_currency_id or line.sku_id.purchase_currency_id
                )

                converted_purchase_price = purchase_currency._convert(
                    line.purchase_price,
                    retail_currency,
                    self.env.company,
                    self.date or fields.Date.context_today(self),
                )
                line.retail_price = converted_purchase_price * coef

    def action_button_validate(self):
        """Validates draft stock records. Posts physical balances directly."""
        for line in self.line_ids:
            if not line.sku_id:
                raise ValidationError(
                    _(
                        "The document cannot be validated because some lines are missing an SKU!"
                    )
                )
            if not line.size_id:
                raise ValidationError(
                    _(
                        "The document cannot be validated because some lines are missing a Size!"
                    )
                )
            if line.retail_price <= 0:
                raise ValidationError(
                    _(
                        "The document cannot be validated without a calculated retail price for SKU %s!"
                    )
                    % line.sku_id.name  # ФІКС: Тепер SKU лежить у полі name картки товару
                )

            line.sku_id.action_generate_stock_lines()

        self.write({"state": "done"})


class ClothReceiptLine(models.Model):
    """Tabular voucher lines dynamically reading parameters from core product cards."""

    _name = "cloth.receipt.line"
    _description = "Goods Receipt Line"

    receipt_id = fields.Many2one(
        "cloth.receipt", ondelete="cascade", string="Parent Receipt"
    )
    product_id = fields.Many2one(
        "cloth.product",
        string="Linked Product",
        compute="_compute_product_id",
        readonly=True,
    )

    @api.depends("sku_id")
    def _compute_product_id(self):
        for line in self:
            line.product_id = line.sku_id.id if line.sku_id else False

    sku_id = fields.Many2one("cloth.product", string="SKU", required=True)

    #  ФІКС: Переводимо поля на compute + store=True для автоматичного заповнення в демо-даних
    name = fields.Char(
        string="Product Name",
        compute="_compute_product_fields",
        store=True,
        readonly=False,
    )
    brand_id = fields.Many2one(
        "cloth.brand",
        string="Brand",
        compute="_compute_product_fields",
        store=True,
        readonly=False,
    )
    collection_id = fields.Many2one(
        "cloth.collection",
        string="Collection",
        compute="_compute_product_fields",
        store=True,
        readonly=False,
    )
    purchase_currency_id = fields.Many2one(
        "res.currency",
        string="Purchase Currency",
        compute="_compute_product_fields",
        store=True,
        readonly=False,
        required=True,
    )

    size_id = fields.Many2one("cloth.size", string="Size", required=True)

    # =========================================================================
    # MULTI-CURRENCY LOGIC INFRASTRUCTURE
    # =========================================================================
    retail_currency_id = fields.Many2one(
        "res.currency",
        string="Retail Currency",
        required=True,
        default=lambda self: self.env.ref("base.UAH").id,
    )

    qty = fields.Integer(string="Quantity", default=1, required=True)
    purchase_price = fields.Monetary(
        string="Purchase Price Unit",
        required=True,
        currency_field="purchase_currency_id",
    )
    retail_price = fields.Monetary(
        string="Retail Price Unit", currency_field="retail_currency_id"
    )

    purchase_subtotal = fields.Monetary(
        string="Purchase Subtotal",
        compute="_compute_subtotals",
        store=True,
        currency_field="purchase_currency_id",
    )
    retail_subtotal = fields.Monetary(
        string="Retail Subtotal",
        compute="_compute_subtotals",
        store=True,
        currency_field="retail_currency_id",
    )

    # 🛠️ НОВИЙ КОМП'ЮТ-МЕТОД замість старого onchange
    @api.depends("sku_id")
    def _compute_product_fields(self):
        for line in self:
            if line.sku_id:
                line.name = line.sku_id.product_title
                line.brand_id = line.sku_id.brand_id
                line.collection_id = line.sku_id.collection_id
                line.purchase_currency_id = (
                    line.sku_id.purchase_currency_id or self.env.company.currency_id
                )
            else:
                line.name = False
                line.brand_id = False
                line.collection_id = False
                line.purchase_currency_id = self.env.company.currency_id

    # Залишаємо тригер для очищення роздрібних цін при ручній зміні закупівлі в інтерфейсі
    @api.onchange("size_id", "qty", "purchase_price", "purchase_currency_id")
    def _onchange_prices_reset(self):
        """Окремий тригер для скидання роздрібних цін при коригуванні закупівлі."""
        self.retail_price = 0.00
        self.retail_subtotal = 0.00

    @api.depends("qty", "purchase_price", "retail_price")
    def _compute_subtotals(self):
        for line in self:
            line.purchase_subtotal = line.qty * line.purchase_price
            line.retail_subtotal = line.qty * line.retail_price
