# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ClothProfitabilityReport(models.Model):
    """
    Automated SQL Analytical View for sales profitability matrix analysis.
    Combines order values, customer discounts, and historical cost layers.
    """

    _name = "cloth.profitability.report"
    _description = "Profitability Report"
    _auto = False
    _order = "date_order desc"

    # Core identification and document fields
    name = fields.Char(string="Order Reference", readonly=True)
    date_order = fields.Datetime(string="Order Date", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    product_id = fields.Many2one("cloth.product", string="Product", readonly=True)
    size_id = fields.Many2one("cloth.size", string="Size", readonly=True)

    # Quantity and purchase cost layers fields
    qty = fields.Integer(string="Quantity", readonly=True)
    purchase_price = fields.Float(
        string="Cost Price Unit",
        readonly=True,
        digits=(12, 2),
    )
    total_cost = fields.Float(string="Total Cost", readonly=True, digits=(12, 2))
    price_unit = fields.Float(string="Retail Price Unit", readonly=True, digits=(12, 2))

    # Discounts and financial net results fields
    discount_percent = fields.Float(string="Discount (%)", readonly=True)
    discount_amount = fields.Float(
        string="Discount Amount",
        readonly=True,
        digits=(12, 2),
    )
    turnover = fields.Float(string="Net Turnover", readonly=True, digits=(12, 2))
    profit = fields.Float(string="Margin Profit", readonly=True, digits=(12, 2))

    def init(self):
        """
        Executes raw PostgreSQL view definitions building the profitability data matrix layers.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    l.id AS id,
                    o.name AS name,
                    o.date_order AS date_order,
                    o.partner_id AS partner_id,
                    l.product_id AS product_id,
                    l.size_id AS size_id,
                    l.qty AS qty,

                    -- COMMENT: Subquery fetches the latest confirmed purchase cost for accurate margins calculations
                    COALESCE((
                        SELECT rl.purchase_price 
                        FROM cloth_receipt_line rl
                        JOIN cloth_receipt r ON r.id = rl.receipt_id
                        WHERE rl.sku_id = l.product_id AND rl.size_id = l.size_id AND r.state = 'done'
                        ORDER BY rl.id DESC LIMIT 1
                    ), 0.00) AS purchase_price,

                    -- Calculating total cost based on purchase cost multiplied by sales quantity metrics
                    COALESCE((
                        SELECT rl.purchase_price 
                        FROM cloth_receipt_line rl
                        JOIN cloth_receipt r ON r.id = rl.receipt_id
                        WHERE rl.sku_id = l.product_id AND rl.size_id = l.size_id AND r.state = 'done'
                        ORDER BY rl.id DESC LIMIT 1
                    ), 0.00) * l.qty AS total_cost,

                    l.price_unit AS price_unit,
                    o.discount AS discount_percent,

                    -- Calculations for absolute financial discounts amounts and final net turnovers fields values
                    (l.price_subtotal * (COALESCE(o.discount, 0.00) / 100.00)) AS discount_amount,
                    (l.price_subtotal * (1.00 - (COALESCE(o.discount, 0.00) / 100.00))) AS turnover,

                    -- Core formula calculating true net profit margins after subtracting cost values from turnover metrics
                    (l.price_subtotal * (1.00 - (COALESCE(o.discount, 0.00) / 100.00))) - 
                    (COALESCE((
                        SELECT rl.purchase_price 
                        FROM cloth_receipt_line rl
                        JOIN cloth_receipt r ON r.id = rl.receipt_id
                        WHERE rl.sku_id = l.product_id AND rl.size_id = l.size_id AND r.state = 'done'
                        ORDER BY rl.id DESC LIMIT 1
                    ), 0.00) * l.qty) AS profit

                FROM cloth_order_line l
                JOIN cloth_order o ON o.id = l.order_id
                WHERE o.state IN ('draft', 'shipped', 'received')
            )
        """)
