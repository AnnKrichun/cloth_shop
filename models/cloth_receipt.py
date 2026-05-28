# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClothReceipt(models.Model):
    """
    Model managing stock intake operations and incoming supplier shipments.
    """

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
        """
        Calculates final store consumer tags using advanced multi-currency conversion paths.
        Driven by direct PrivatBank cross-rate matrices, completely bypassing core database flaws.
        Formula: (Purchase Price / Purchase Rate * Retail Rate) * Markup Multiplier.
        """
        stored_param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cloth_shop.retail_currency_id")
        )

        if stored_param and stored_param.isdigit():
            retail_currency = self.env["res.currency"].browse(int(stored_param))
        else:
            retail_currency = self.env.company.currency_id

        company = self.env.company
        today_date = self.date or fields.Date.today()

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

                # 1. Fetch system Odoo rate parameters recorded for RETAIL currency and PURCHASE currency
                rate_retail = self.env["res.currency.rate"].search(
                    [
                        ("currency_id", "=", retail_currency.id),
                        ("name", "<=", today_date),
                        ("company_id", "=", company.id),
                    ],
                    order="name desc",
                    limit=1,
                )

                rate_purchase = self.env["res.currency.rate"].search(
                    [
                        ("currency_id", "=", purchase_currency.id),
                        ("name", "<=", today_date),
                        ("company_id", "=", company.id),
                    ],
                    order="name desc",
                    limit=1,
                )

                # 2. FIXED EVALUATION: Safe cross-rate transition based on Odoo standard base-currency inversion
                if rate_retail and rate_purchase and rate_purchase.rate > 0:
                    # Математично: (Ціна закупівлі / Курс закупівлі) отримуємо чистий USD.
                    # Потім отриманий USD * Курс роздрібу = ціна у валюті роздрібу (UAH).
                    purchase_price_in_retail = (
                        line.purchase_price / rate_purchase.rate
                    ) * rate_retail.rate
                else:
                    # Fallback to standard native _convert if rate history logs are missing
                    purchase_price_in_retail = purchase_currency._convert(
                        line.purchase_price,
                        retail_currency,
                        company,
                        today_date,
                    )

                # 3. FINAL COMPUTATION: Cost price converted to retail currency multiplied by margin rule
                line.retail_price = purchase_price_in_retail * coef

    def action_button_validate(self):
        """
        Validates draft stock records. Posts physical balances directly.
        Synchronizes newly calculated prices into the global matrix (cloth.product.price).
        """
        for line in self.line_ids:
            if not line.sku_id:
                raise ValidationError(
                    _(
                        "The document cannot be validated because some lines are missing an SKU!"
                    )
                )

            if line.retail_price <= 0:
                raise ValidationError(
                    _(
                        "The document cannot be validated without a calculated retail price for SKU %s!"
                    )
                    % line.sku_id.name
                )

        # Force a fresh retail prices evaluation sequence right before posting to ensure actual market metrics
        self.action_calculate_retail_prices()

        # 🔒 COMPLEX LOGIC INTEGRATION: Synchronize retail prices to cloth.product.price matrix
        for line in self.line_ids:
            # Look for an existing price configuration entry for this specific SKU + Size combo
            price_record = self.env["cloth.product.price"].search(
                [
                    ("product_id", "=", line.sku_id.id),
                    ("size_id", "=", line.size_id.id),
                ],
                limit=1,
            )

            if price_record:
                # Update the active price entry in the database matrix
                price_record.write({"retail_price": line.retail_price})
            else:
                # Instantiate a clean core database entry row
                self.env["cloth.product.price"].create(
                    {
                        "product_id": line.sku_id.id,
                        "size_id": line.size_id.id,
                        "retail_price": line.retail_price,
                    }
                )

        self.write({"state": "done"})


class ClothReceiptLine(models.Model):
    """
    Tabular voucher lines dynamically reading parameters from core product cards.
    """

    _name = "cloth.receipt.line"
    _description = "Goods Receipt Line"

    receipt_id = fields.Many2one(
        "cloth.receipt", ondelete="cascade", string="Parent Receipt"
    )

    # REMOVED store=True to prevent registry initialization recursion deadlocks
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

    # REFERENCE DATA FIELDS (RELATED): Pull parameters automatically from product profile card as read-only
    name = fields.Char(related="sku_id.name", string="Product Name", readonly=True)
    brand_id = fields.Many2one(related="sku_id.brand_id", string="Brand", readonly=True)
    collection_id = fields.Many2one(
        related="sku_id.collection_id", string="Collection", readonly=True
    )

    # Converted from a related field to a direct Many2one link to fit the new size-matrix design
    size_id = fields.Many2one("cloth.size", string="Size", required=True)

    # =========================================================================
    # MULTI-CURRENCY LOGIC INFRASTRUCTURE
    # =========================================================================
    purchase_currency_id = fields.Many2one(
        "res.currency", string="Purchase Currency", required=True
    )

    retail_currency_id = fields.Many2one(
        "res.currency",
        string="Retail Currency",
        required=True,
        default=lambda self: self.env.ref("base.UAH").id,
    )

    # INPUT DATA FIELDS: Price unit parameters re-mapped to native monetary field attributes
    qty = fields.Integer(string="Quantity", default=1, required=True)

    purchase_price = fields.Monetary(
        string="Purchase Price Unit",
        required=True,
        currency_field="purchase_currency_id",
    )
    retail_price = fields.Monetary(
        string="Retail Price Unit", currency_field="retail_currency_id"
    )

    # COMPUTED SUB-FINANCIAL SUBTOTAL FIELDS: Automatically evaluated upon quantities input updates
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

    # 🆕 ПОВЕРНЕНО МЕТОД ДЛЯ РОЗРАХУНКУ ДЕМО-ДАНИХ XML:
    @api.model
    def _compute_product_fields(self, record_ids=None):
        if record_ids:
            # Знаходимо наші демо-рядки в базі за їхніми ID
            lines = self.browse(record_ids)
            for line in lines:
                if line.receipt_id:
                    # Запускаємо для них наш правильний розрахунок цін за курсом ПриватБанку
                    line.receipt_id.action_calculate_retail_prices()
        return True

    @api.onchange("sku_id", "qty", "purchase_price", "purchase_currency_id")
    def _onchange_sku_id(self):
        """
        Triggers instantly upon any grid parameters mutation.
        Strictly RESETS retail pricing metrics on any core input modifications.
        Pulls correct textual Product Name instead of overriding it with SKU code.
        """
        # КРОК 1: Роздрібна ціна та її субтотал обов'язково обнуляються при будь-якій мутації полів
        self.retail_price = 0.00
        self.retail_subtotal = 0.00

        if self.sku_id:
            # Якщо це новий рядок, який щойно створили, або якщо артикул реально змінили на інший:
            if not self._origin or self._origin.sku_id != self.sku_id:
                # Перевіряємо, чи ми міняємо артикул, чи просто вводимо ціну.
                # Якщо користувач уже ввів якусь ціну руками, ми її не затираємо!
                if not self.purchase_price:
                    self.purchase_currency_id = self.sku_id.purchase_currency_id.id
                    # ФІКС: Підтягуємо текстову назву моделі товарів замість коду артикулу
                    self.name = self.sku_id.product_title
                    self.purchase_price = 0.00  # Скидаємо закупку в 0 тільки при первинному виборі артикулу
            else:
                # Якщо артикул не мінявся (користувач ввів ціну чи кількість), ми просто підтягуємо ім'я
                # ФІКС: Аналогічно беремо product_title
                self.name = self.sku_id.product_title
        else:
            self.purchase_currency_id = self.env.company.currency_id.id
            self.name = False
            self.purchase_price = 0.00

    @api.depends("qty", "purchase_price", "retail_price")
    def _compute_subtotals(self):
        """
        Dynamically evaluates immediate row financial values in real-time.
        Formula: Quantity * Price Unit.
        """
        for line in self:
            line.purchase_subtotal = line.qty * line.purchase_price
            line.retail_subtotal = line.qty * line.retail_price
