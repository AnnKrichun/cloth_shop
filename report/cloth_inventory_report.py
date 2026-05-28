# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ClothInventoryReport(models.Model):
    """
    Automated SQL Analytical View for Inventory Stock Flows and Size-Matrix Valuation Operations.
    """

    _name = "cloth.inventory.report"
    _description = "Inventory Turnover and Stock Report"
    _auto = False
    _order = "date desc, product_id asc"

    # =========================================================================
    # CORE DIMENSIONS & TIME FILTERS
    # =========================================================================
    date = fields.Date(string="Operation Date", readonly=True)
    report_period = fields.Selection(
        [("last_month", "Last 30 Days"), ("older", "Older Data")],
        string="Report Period",
        readonly=True,
    )

    product_id = fields.Many2one("cloth.product", string="Product SKU", readonly=True)
    sku = fields.Char(string="SKU Code", readonly=True)
    brand_id = fields.Many2one("cloth.brand", string="Brand", readonly=True)
    collection_id = fields.Many2one(
        "cloth.collection",
        string="Collection",
        readonly=True,
    )
    size_id = fields.Many2one("cloth.size", string="Size", readonly=True)

    # Combined system source document tracking parameters
    doc_name = fields.Char(string="Document", readonly=True)
    res_model = fields.Char(string="Resource Model", readonly=True)
    res_id = fields.Integer(string="Resource ID", readonly=True)

    # =========================================================================
    # QUANTITY TURNOVER METRICS
    # =========================================================================
    qty_incoming = fields.Integer(string="Qty Received (In)", readonly=True)
    qty_outgoing = fields.Integer(string="Qty Shipped (Out)", readonly=True)
    qty_balance = fields.Integer(string="Current Stock Balance", readonly=True)

    # =========================================================================
    # FINANCIAL VALUE TURNOVER METRICS
    # =========================================================================
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    purchase_value = fields.Monetary(
        string="Total Purchase Value",
        readonly=True,
        currency_field="currency_id",
    )
    retail_value = fields.Monetary(
        string="Total Retail Sales Value",
        readonly=True,
        currency_field="currency_id",
    )
    retail_price = fields.Monetary(
        string="Current Retail Price",
        readonly=True,
        currency_field="currency_id",
        aggregator="avg",
    )

    def action_open_source_document(self):
        """
        Dynamically opens the original form view of the linked source record.
        """
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False

        return {
            "type": "ir.actions.act_window",
            "name": self.doc_name,
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    def init(self):
        """
        Executes raw PostgreSQL view definitions building the entire analytical data cube layers.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    ROW_NUMBER() OVER () AS id,
                    p.id AS product_id,
                    p.name AS sku,
                    p.brand_id AS brand_id,
                    p.collection_id AS collection_id,
                    move_data.size_id AS size_id,
                    move_data.date AS date,

                    CASE 
                        WHEN move_data.date >= CURRENT_DATE - INTERVAL '30 days' THEN 'last_month'
                        ELSE 'older'
                    END AS report_period,

                    move_data.doc_name AS doc_name,
                    move_data.res_model AS res_model,
                    move_data.res_id AS res_id,

                    move_data.qty_incoming AS qty_incoming,
                    move_data.purchase_value AS purchase_value,
                    move_data.qty_outgoing AS qty_outgoing,
                    move_data.retail_value AS retail_value,
                    move_data.qty_balance AS qty_balance,
                    (SELECT id FROM res_currency WHERE name = 'UAH' LIMIT 1) AS currency_id,

                    COALESCE((
                        SELECT sub_rl.retail_price 
                        FROM cloth_receipt_line sub_rl
                        JOIN cloth_receipt sub_r ON sub_r.id = sub_rl.receipt_id
                        WHERE sub_rl.sku_id = p.id AND sub_rl.size_id = move_data.size_id AND sub_r.state = 'done'
                        ORDER BY sub_rl.id DESC 
                        LIMIT 1
                    ), 0.00) AS retail_price

                FROM cloth_product p
                JOIN (
                    -- PART 1: Goods Receipts Documents
                    SELECT 
                        rl.sku_id AS product_id,
                        rl.size_id AS size_id,
                        r.date::date AS date,
                        r.name AS doc_name,
                        'cloth.receipt' AS res_model,
                        r.id AS res_id,
                        rl.qty AS qty_incoming,
                        rl.purchase_subtotal AS purchase_value,
                        0 AS qty_outgoing,
                        0.00 AS retail_value,
                        rl.qty AS qty_balance
                    FROM cloth_receipt_line rl
                    JOIN cloth_receipt r ON r.id = rl.receipt_id
                    WHERE r.state = 'done'

                    UNION ALL

                    -- PART 2: Customer Orders Documents
                    SELECT 
                        ol.product_id AS product_id,
                        ol.size_id AS size_id,
                        o.date_order::date AS date,
                        o.name AS doc_name,
                        'cloth.order' AS res_model,
                        o.id AS res_id,
                        0 AS qty_incoming,
                        0.00 AS purchase_value,
                        ol.qty AS qty_outgoing,
                        ol.price_subtotal AS retail_value,
                        -ol.qty AS qty_balance
                    FROM cloth_order_line ol
                    JOIN cloth_order o ON o.id = ol.order_id
                    WHERE o.state IN ('shipped', 'received')
                ) AS move_data ON move_data.product_id = p.id
            )
        """)
