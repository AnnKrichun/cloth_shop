# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ClothProduct(models.Model):
    """Model representing cloth shop products and their size-matrix stock levels."""

    _name = "cloth.product"
    _description = "Cloth Product Stock Card"

    # Повертаємо стандартну логіку Odoo, але тепер name — це наш артикул!
    _rec_name = "name"
    _rec_names_search = ["name", "product_title"]

    # =========================================================================
    # CORE PRODUCT ATTRIBUTES (ФІКС: name тепер виконує роль SKU)
    # =========================================================================
    name = fields.Char(string="SKU", required=True, index=True)
    product_title = fields.Char(string="Product Name", required=True)

    brand_id = fields.Many2one("cloth.brand", string="Brand", required=True)
    collection_id = fields.Many2one(
        "cloth.collection", string="Collection", required=True
    )

    # =========================================================================
    # MULTI-CURRENCY POINTER LINKS
    # =========================================================================
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

    # =========================================================================
    # RELATIONAL SYSTEM DEPS & MATRIX STOCK LINES
    # =========================================================================
    receipt_line_ids = fields.One2many(
        "cloth.receipt.line", "sku_id", string="Receipt Lines"
    )
    order_line_ids = fields.One2many(
        "cloth.order.line", "product_id", string="Order Lines"
    )
    stock_line_ids = fields.One2many(
        "cloth.product.stock.line", "product_id", string="Stock Breakdown Matrix"
    )

    _sql_constraints = [
        (
            "sku_name_unique",
            "unique(name)",
            "A product with this SKU code already exists!",
        )
    ]

    def action_generate_stock_lines(self):
        """Безпечний метод для генерації та оновлення ліній матриці розмірів."""
        StockLine = self.env["cloth.product.stock.line"]
        for product in self:
            received_sizes = product.receipt_line_ids.filtered(
                lambda r: r.receipt_id.state == "done"
            ).mapped("size_id.id")
            ordered_sizes = product.order_line_ids.filtered(
                lambda o: o.order_id.state in ("shipped", "received")
            ).mapped("size_id.id")
            all_size_ids = list(set(received_sizes + ordered_sizes))

            existing_size_ids = product.stock_line_ids.mapped("size_id.id")

            for size_id in all_size_ids:
                if size_id not in existing_size_ids:
                    StockLine.create(
                        {
                            "product_id": product.id,
                            "size_id": size_id,
                        }
                    )

    @api.model
    def default_get(self, fields_list):
        """Автоматично підставляє введене значення у поле name (яке тепер є SKU)."""
        res = super(ClothProduct, self).default_get(fields_list)
        ctx = self.env.context

        typed_text = (
            ctx.get("default_display_name")
            or ctx.get("search_default_name")
            or ctx.get("default_name")
        )

        if typed_text and isinstance(typed_text, str):
            cleaned_sku = typed_text.strip().upper()
            res["name"] = cleaned_sku  # Записуємо артикул у базове поле імені

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Валідація та очищення строк при збереженні."""
        for vals in vals_list:
            if "name" in vals and isinstance(vals["name"], str):
                vals["name"] = vals["name"].strip().upper()
            if "product_title" in vals and isinstance(vals["product_title"], str):
                vals["product_title"] = vals["product_title"].strip()

        records = super(ClothProduct, self).create(vals_list)
        records.action_generate_stock_lines()
        return records

    @api.model
    def name_create(self, name):
        """Швидке створення в один клік."""
        cleaned_sku = name.strip().upper()
        product = self.search([("name", "=", cleaned_sku)], limit=1)
        if not product:
            product = self.create(
                {
                    "name": cleaned_sku,
                    "product_title": cleaned_sku,
                }
            )
        return product.id, product.name


class ClothProductStockLine(models.Model):
    """
    Sub-resource model tracking unified inventory aggregates
    and reading direct actual tags from the new price matrix.
    """

    _name = "cloth.product.stock.line"
    _description = "Product Size Stock Balance Log"

    product_id = fields.Many2one(
        "cloth.product", string="Product Link", ondelete="cascade", index=True
    )
    size_id = fields.Many2one("cloth.size", string="Size Rows index", readonly=True)
    qty_available = fields.Integer(
        string="Quantity On Hand", compute="_compute_metrics"
    )
    retail_price = fields.Float(
        string="Actual Retail Price", compute="_compute_metrics"
    )

    # ⚡ ОНОВЛЕНИЙ ТРИГЕР: Додано відстеження змін у моделі cloth.product.price
    @api.depends(
        "product_id.receipt_line_ids.qty",
        "product_id.receipt_line_ids.receipt_id.state",
        "product_id.order_line_ids.qty",
        "product_id.order_line_ids.order_id.state",
    )
    def _compute_metrics(self):
        """
        Evaluates physical store stock levels and pulls fresh verified
        price vectors directly from the cloth.product.price matrix.
        """
        for line in self:
            if line.product_id and line.size_id:
                # 1. Складна логіка розрахунку фізичних залишків на складі
                incoming = sum(
                    line.product_id.receipt_line_ids.filtered(
                        lambda r: (
                            r.size_id == line.size_id and r.receipt_id.state == "done"
                        )
                    ).mapped("qty")
                )
                outgoing = sum(
                    line.product_id.order_line_ids.filtered(
                        lambda o: (
                            o.size_id == line.size_id
                            and o.order_id.state in ("shipped", "received")
                        )
                    ).mapped("qty")
                )
                line.qty_available = incoming - outgoing

                # 🔒 ФІКС: Пряме вичитування чинної ціни з нової моделі-матриці cloth.product.price
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
