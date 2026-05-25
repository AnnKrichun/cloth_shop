# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ClothProduct(models.Model):
    """
    Model representing cloth shop products and their size-matrix stock levels.
    """

    _name = "cloth.product"
    _description = "Cloth Product Stock Card"

    # Strictly bind Odoo 19 core views generation handlers onto the unique SKU column slot
    _rec_name = "sku"

    _rec_names_search = ["sku"]
    # =========================================================================
    # CORE PRODUCT ATTRIBUTES
    # =========================================================================
    sku = fields.Char(string="SKU", required=True, index=True)
    name = fields.Char(string="Product Name", required=True)
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
        "cloth.product.stock.line",
        "product_id",
        string="Stock Breakdown Matrix",
        compute="_compute_stock_lines",
    )

    _sql_constraints = [
        ("sku_unique", "unique(sku)", "A product with this SKU code already exists!")
    ]

    def _compute_stock_lines(self):
        for product in self:
            received_sizes = product.receipt_line_ids.filtered(
                lambda r: r.receipt_id.state == "done"
            ).mapped("size_id.id")
            ordered_sizes = product.order_line_ids.filtered(
                lambda o: o.order_id.state in ("shipped", "received")
            ).mapped("size_id.id")
            all_size_ids = list(set(received_sizes + ordered_sizes))

            existing_lines = self.env["cloth.product.stock.line"].search(
                [("product_id", "=", product.id)]
            )
            existing_size_ids = existing_lines.mapped("size_id.id")

            for size_id in all_size_ids:
                if size_id not in existing_size_ids:
                    self.env["cloth.product.stock.line"].create(
                        {
                            "product_id": product.id,
                            "size_id": size_id,
                        }
                    )

            product.stock_line_ids = self.env["cloth.product.stock.line"].search(
                [("product_id", "=", product.id)]
            )

    @api.depends("sku")
    def _compute_display_name(self):
        """
        Примушує систему на всіх етапах відображати
        в Many2one полі тільки артикул (код).
        """
        for product in self:
            product.display_name = product.sku or "New Alphanumeric Code"

    def name_get(self):
        """
        ГОЛОВНИЙ ФІКС ДЛЯ ВЕБ-КЛІЄНТА JAVASCRIPT:
        Цей метод викликається фронтендом Odoo в момент натискання кнопки "Save"
        у вікні створення. Він примусово каже браузеру:
        "Візьми для відображення в Many2one стовпчику тільки артикул (sku)!"
        """
        res = []
        for product in self:
            res.append((product.id, product.sku or "New Alphanumeric Code"))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        БЛОКУВАННЯ КОПІЮВАННЯ: Суворо зберігає ту назву, яку користувач
        ввів руками (name) у поп-апі. Копіювання артикула в назву заборонено.
        """
        for vals in vals_list:
            if "name" in vals and isinstance(vals["name"], str) and vals["name"]:
                vals["name"] = vals["name"].strip()

            # Фолбек тільки якщо поле name прийшло абсолютно порожнім
            elif "sku" in vals and not vals.get("name"):
                vals["name"] = vals["sku"]

        records = super(ClothProduct, self).create(vals_list)
        return records

    @api.model
    def name_create(self, name):
        """
        Забезпечує повернення чистих даних (id, sku) для фронтенду
        при швидкому зв'язуванні на льоту.
        """
        cleaned_sku = name.strip().upper()
        product = self.search([("sku", "=", cleaned_sku)], limit=1)
        if not product:
            product = self.create(
                {
                    "sku": cleaned_sku,
                    "name": cleaned_sku,
                }
            )
        return product.id, product.display_name

    @api.model
    def _name_search(self, name, domain=None, operator="ilike", limit=100, order=None):
        """
        Суворий пошук в базі даних ВИКЛЮЧНО за артикулом (sku).
        Пошук за назвою моделі одягу повністю вимкнено.
        """
        domain = domain or []
        if name:
            domain = [("sku", operator, name)] + domain
        return super()._name_search(name, domain, operator, limit, order)

    @api.model
    def default_get(self, fields_list):
        """
        Intercepts context parameters and routes the values directly into the SKU code column slot.
        """
        res = super(ClothProduct, self).default_get(fields_list)
        ctx = self.env.context

        typed_text = (
            ctx.get("default_sku")
            or ctx.get("default_name")
            or ctx.get("search_default_sku")
            or ctx.get("search_default_name")
        )

        if typed_text and isinstance(typed_text, str):
            cleaned_sku = typed_text.strip().upper()
            res["sku"] = cleaned_sku
            res["name"] = False

        return res


class ClothProductStockLine(models.Model):
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

    @api.depends(
        "product_id.receipt_line_ids.qty",
        "product_id.receipt_line_ids.receipt_id.state",
        "product_id.order_line_ids.qty",
        "product_id.order_line_ids.order_id.state",
    )
    def _compute_metrics(self):
        for line in self:
            if line.product_id and line.size_id:
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

                latest_receipt = self.env["cloth.receipt.line"].search(
                    [
                        ("sku_id", "=", line.product_id.id),
                        ("size_id", "=", line.size_id.id),
                        ("receipt_id.state", "=", "done"),
                    ],
                    order="id desc",
                    limit=1,
                )
                line.retail_price = (
                    latest_receipt.retail_price if latest_receipt else 0.00
                )
            else:
                line.qty_available = 0
                line.retail_price = 0.00
