# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ClothReceipt(models.Model):
    """
    Model for managing stock receipts from suppliers.
    Handles automatic code sequences, currency math, and pricing updates.
    """

    _name = "cloth.receipt"
    _description = "Goods Receipt Note"
    _order = "date desc, id desc"

    # Core identification and tracking fields
    name = fields.Char(
        string="Document Number",
        required=True,
        readonly=True,
        default=lambda self: _("New"),
    )
    date = fields.Date(string="Date", default=fields.Date.context_today, required=True)
    line_ids = fields.One2many(
        "cloth.receipt.line",
        "receipt_id",
        string="Product Lines",
    )

    # State selection ledger
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Validated")],
        string="Status",
        default="draft",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Generates a unique document code from the system sequence configuration.
        """
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "cloth.receipt",
                ) or _("New")
        return super().create(vals_list)

    def action_calculate_retail_prices(self):
        """
        Calculates store retail prices based on currency rates and markups.
        Formula: (Purchase Price / Purchase Rate * Retail Rate) * Markup Multiplier.
        """
        # COMMENT: Read the system retail currency parameter setup from settings
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
                # COMMENT: Search for the dynamic profit margin rule in coefficients database
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

                # COMMENT: Fetch active currency rates from the database logs
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

                # COMMENT: Convert purchase price into store retail currency format
                if rate_retail and rate_purchase and rate_purchase.rate > 0:
                    purchase_price_in_retail = (
                        line.purchase_price / rate_purchase.rate
                    ) * rate_retail.rate
                else:
                    purchase_price_in_retail = purchase_currency._convert(
                        line.purchase_price,
                        retail_currency,
                        company,
                        today_date,
                    )

                # Apply multiplier coefficient to establish the final retail price tag
                line.retail_price = purchase_price_in_retail * coef

    def action_button_validate(self):
        """
        Validates the document, locks states, and injects prices into the main matrix.
        """
        # COMMENT: Verification loop preventing validation with empty or wrong fields data
        for line in self.line_ids:
            if not line.sku_id:
                raise ValidationError(
                    _(
                        "The document cannot be validated because some lines are missing an SKU!",
                    ),
                )

            if line.retail_price <= 0:
                raise ValidationError(
                    _(
                        "The document cannot be validated without a calculated retail price for SKU %s!",
                    )
                    % line.sku_id.name,
                )

        # Force price calculation routine to ensure numbers are updated
        self.action_calculate_retail_prices()

        # COMMENT: Write or create new price entries inside the global matrix model layout
        for line in self.line_ids:
            price_record = self.env["cloth.product.price"].search(
                [
                    ("product_id", "=", line.sku_id.id),
                    ("size_id", "=", line.size_id.id),
                ],
                limit=1,
            )

            if price_record:
                price_record.write({"retail_price": line.retail_price})
            else:
                self.env["cloth.product.price"].create(
                    {
                        "product_id": line.sku_id.id,
                        "size_id": line.size_id.id,
                        "retail_price": line.retail_price,
                    },
                )

        # Successfully transition the document status ledger
        self.write({"state": "done"})


class ClothReceiptLine(models.Model):
    """
    Model representing individual items lines inside a goods receipt note.
    Tracks quantities, sizes, purchase costs, and computed retail prices.
    """

    _name = "cloth.receipt.line"
    _description = "Goods Receipt Line"

    receipt_id = fields.Many2one(
        "cloth.receipt",
        ondelete="cascade",
        string="Parent Receipt",
    )

    product_id = fields.Many2one(
        "cloth.product",
        string="Linked Product",
        compute="_compute_product_id",
        readonly=True,
    )

    sku_id = fields.Many2one("cloth.product", string="SKU", required=True)

    # Fields automatically mirroring properties from the main product card
    name = fields.Char(related="sku_id.name", string="Product Name", readonly=True)
    brand_id = fields.Many2one(related="sku_id.brand_id", string="Brand", readonly=True)
    collection_id = fields.Many2one(
        related="sku_id.collection_id",
        string="Collection",
        readonly=True,
    )

    size_id = fields.Many2one("cloth.size", string="Size", required=True)

    # Multi-currency matrix fields
    purchase_currency_id = fields.Many2one(
        "res.currency",
        string="Purchase Currency",
        required=True,
    )

    retail_currency_id = fields.Many2one(
        "res.currency",
        string="Retail Currency",
        required=True,
        default=lambda self: self.env.ref("base.UAH").id,
    )

    qty = fields.Integer(string="Quantity", default=1, required=True)

    # Financial price units tracking
    purchase_price = fields.Monetary(
        string="Purchase Price Unit",
        required=True,
        currency_field="purchase_currency_id",
    )
    retail_price = fields.Monetary(
        string="Retail Price Unit",
        currency_field="retail_currency_id",
    )

    # Computed financial values fields
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

    @api.depends("sku_id")
    def _compute_product_id(self):
        """Assigns backend product link identification based on chosen SKU."""
        for line in self:
            line.product_id = line.sku_id.id if line.sku_id else False

    @api.model
    def _compute_product_fields(self, record_ids=None):
        """
        Technical helper method used by demo data triggers to calculate retail prices.
        """
        if record_ids:
            lines = self.browse(record_ids)
            for line in lines:
                if line.receipt_id:
                    line.receipt_id.action_calculate_retail_prices()
        return True

    @api.onchange("sku_id", "qty", "purchase_price", "purchase_currency_id")
    def _onchange_sku_id(self):
        """
        Resets retail values and auto-fills default purchase currency upon product change.
        """
        # COMMENT: Clear retail fields to prevent showing old data configurations
        self.retail_price = 0.00
        self.retail_subtotal = 0.00

        if self.sku_id:
            if not self._origin or self._origin.sku_id != self.sku_id:
                if not self.purchase_price:
                    # COMMENT: Prefill currency parameters from master product card setup
                    self.purchase_currency_id = self.sku_id.purchase_currency_id.id
                    self.name = self.sku_id.product_title
                    self.purchase_price = 0.00
            else:
                self.name = self.sku_id.product_title
        else:
            self.purchase_currency_id = self.env.company.currency_id.id
            self.name = False
            self.purchase_price = 0.00

    @api.depends("qty", "purchase_price", "retail_price")
    def _compute_subtotals(self):
        """
        Calculates line subtotals by multiplying item quantities by their specific unit prices.
        """
        for line in self:
            line.purchase_subtotal = line.qty * line.purchase_price
            line.retail_subtotal = line.qty * line.retail_price
