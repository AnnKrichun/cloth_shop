import logging

from odoo import api, fields, models

# Logger initialization for banking background tasks
_logger = logging.getLogger(__name__)


class ClothProduct(models.Model):
    """
    Model representing cloth shop products and their size-matrix stock levels.
    """

    _name = "cloth.product"
    _description = "Cloth Product Stock Card"

    _rec_name = "name"
    _rec_names_search = ["name", "product_title"]

    # Core identification fields
    name = fields.Char(string="SKU", required=True, index=True)
    product_title = fields.Char(string="Product Name", required=True)

    brand_id = fields.Many2one("cloth.brand", string="Brand", required=True)
    collection_id = fields.Many2one(
        "cloth.collection",
        string="Collection",
        required=True,
    )

    # Multi-currency and company configuration fields
    purchase_currency_id = fields.Many2one(
        "res.currency",
        string="Default Purchase Currency",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    retail_currency_id = fields.Many2one(
        "res.currency",
        string="Store Retail Currency",
        required=True,
        default=lambda self: self.env.ref("base.UAH").id,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # Relational lines vectors
    receipt_line_ids = fields.One2many(
        "cloth.receipt.line",
        "sku_id",
        string="Receipt Lines",
    )
    order_line_ids = fields.One2many(
        "cloth.order.line",
        "product_id",
        string="Order Lines",
    )
    stock_line_ids = fields.One2many(
        "cloth.product.stock.line",
        "product_id",
        string="Stock Breakdown Matrix",
    )

    # Structural constraint blocking duplicate codes in database
    _sql_constraints = [
        (
            "sku_name_unique",
            "unique(name)",
            "A product with this SKU code already exists!",
        ),
    ]

    def action_generate_stock_lines(self):
        """
        Scans all validated documents to generate size layout rows in the matrix.
        """
        StockLine = self.env["cloth.product.stock.line"]
        for product in self:
            # COMMENT: Find all unique size IDs from completed receipts and orders
            received_sizes = product.receipt_line_ids.filtered(
                lambda r: r.receipt_id.state == "done",
            ).mapped("size_id.id")
            ordered_sizes = product.order_line_ids.filtered(
                lambda o: o.order_id.state in ("shipped", "received"),
            ).mapped("size_id.id")
            all_size_ids = list(set(received_sizes + ordered_sizes))

            existing_size_ids = product.stock_line_ids.mapped("size_id.id")

            # COMMENT: Create missing rows if they do not exist yet
            for size_id in all_size_ids:
                if size_id not in existing_size_ids:
                    StockLine.create(
                        {
                            "product_id": product.id,
                            "size_id": size_id,
                        },
                    )

    @api.model
    def default_get(self, fields_list):
        """
        Interceptors context text to pre-fill SKU names automatically.
        """
        res = super().default_get(fields_list)
        ctx = self.env.context

        typed_text = (
            ctx.get("default_display_name")
            or ctx.get("search_default_name")
            or ctx.get("default_name")
        )

        if typed_text and isinstance(typed_text, str):
            cleaned_sku = typed_text.strip().upper()
            # COMMENT: Saves cleaned text directly into the main SKU name field
            res["name"] = cleaned_sku

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        Cleans data formatting inputs and runs matrix population on creation.
        """
        for vals in vals_list:
            if "name" in vals and isinstance(vals["name"], str):
                vals["name"] = vals["name"].strip().upper()
            if "product_title" in vals and isinstance(vals["product_title"], str):
                vals["product_title"] = vals["product_title"].strip()

        records = super().create(vals_list)
        records.action_generate_stock_lines()
        return records

    @api.model
    def name_create(self, name):
        """
        Enables inline creation support inside selection lookups fields.
        """
        cleaned_sku = name.strip().upper()
        product = self.search([("name", "=", cleaned_sku)], limit=1)
        if not product:
            product = self.create(
                {
                    "name": cleaned_sku,
                    "product_title": cleaned_sku,
                },
            )
        return product.id, product.name

    @api.model
    def search(
        self,
        args,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ):
        """
        ⚡ AUTOMATED DAILY EXCHANGE RATES TRIGGER:
        Intercepts record search upon interface loading to check and sync currency rates.
        Strictly secures and isolates database transactions from deadlocks during installation.
        """
        if (
            self.env.registry.ready
            and not self.env.context.get("install_demo")
            and self.env.user.id != 1
        ):
            if not self.env.context.get(
                "plugin_install_mode",
            ) and not self.env.context.get("install_mode"):
                today_date = fields.Date.today()

                today_rate_exists = self.env["res.currency.rate"].search_count(
                    [("name", "=", today_date), ("is_privatbank_rate", "=", True)],
                )

                if not today_rate_exists:
                    _logger.info(
                        "AUTOMATED LIVE SYNC INITIATED: Missing exchange logs for %s. Reaching out to bank API...",
                        today_date,
                    )
                    try:
                        self.env["res.currency"]._update_privatbank_currency_rates()
                    except Exception as e:
                        _logger.error(
                            "Automated check failed to overwrite session parameters: %s",
                            str(e),
                        )

        return super().search(
            args,
            offset=offset,
            limit=limit,
            order=order,
        )


class ClothProductStockLine(models.Model):
    """
    Sub-resource model tracking unified inventory aggregates
    and reading prices from the retail price matrix.
    """

    _name = "cloth.product.stock.line"
    _description = "Product Size Stock Balance Log"

    product_id = fields.Many2one(
        "cloth.product",
        string="Product Link",
        ondelete="cascade",
        index=True,
    )
    size_id = fields.Many2one("cloth.size", string="Size", readonly=True)
    qty_available = fields.Integer(
        string="Quantity On Hand",
        compute="_compute_metrics",
    )
    retail_price = fields.Float(
        string="Actual Retail Price",
        compute="_compute_metrics",
    )

    @api.depends(
        "product_id.receipt_line_ids.qty",
        "product_id.receipt_line_ids.receipt_id.state",
        "product_id.order_line_ids.qty",
        "product_id.order_line_ids.order_id.state",
    )
    def _compute_metrics(self):
        """
        Calculates physical warehouse stock levels and fetches
        the current retail price from the configuration matrix.
        """
        for line in self:
            if line.product_id and line.size_id:
                # COMMENT: Calculate total incoming items from completed receipts
                incoming = sum(
                    line.product_id.receipt_line_ids.filtered(
                        lambda r: (
                            r.size_id == line.size_id and r.receipt_id.state == "done"
                        ),
                    ).mapped("qty"),
                )

                # COMMENT: Calculate total outgoing items from shipped or received orders
                outgoing = sum(
                    line.product_id.order_line_ids.filtered(
                        lambda o: (
                            o.size_id == line.size_id
                            and o.order_id.state in ("shipped", "received")
                        ),
                    ).mapped("qty"),
                )

                # Core inventory math formula
                line.qty_available = incoming - outgoing

                # COMMENT: Pull the active retail price record directly from the pricing matrix
                price_record = self.env["cloth.product.price"].search(
                    [
                        ("product_id", "=", line.product_id.id),
                        ("size_id", "=", line.size_id.id),
                    ],
                    limit=1,
                )

                line.retail_price = price_record.retail_price if price_record else 0.00
            else:
                line.qty_available = 0
                line.retail_price = 0.00
