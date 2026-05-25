# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class ClothInventoryReport(models.Model):
    """
    Automated SQL Analytical View for Inventory Stock Flows and Size-Matrix Valuation Operations.
    """

    _name = "cloth.inventory.report"
    _description = "Inventory Turnover and Stock Report"
    _auto = False
    _order = "sku asc"

    # =========================================================================
    # CORE DIMENSIONS
    # =========================================================================
    product_id = fields.Many2one("cloth.product", string="Product SKU", readonly=True)
    sku = fields.Char(string="SKU Code", readonly=True)
    brand_id = fields.Many2one("cloth.brand", string="Brand", readonly=True)
    collection_id = fields.Many2one(
        "cloth.collection", string="Collection", readonly=True
    )
    size_id = fields.Many2one("cloth.size", string="Size", readonly=True)

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
        string="Total Purchase Value", readonly=True, currency_field="currency_id"
    )
    retail_value = fields.Monetary(
        string="Total Retail Sales Value", readonly=True, currency_field="currency_id"
    )

    # 🛠️ FIXED FOR ODOO 19: Displays current size-specific retail price calculated from the latest receipt
    retail_price = fields.Monetary(
        string="Current Retail Price",
        readonly=True,
        currency_field="currency_id",
        aggregator="avg",
    )

    def init(self):
        """
        Executes raw PostgreSQL view definitions building the entire analytical data cube layers.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    -- 🛠️ Surrogate Unique Row ID for complex multi-dimension grouping views
                    ROW_NUMBER() OVER () AS id,
                    p_data.product_id AS product_id,
                    p_data.sku AS sku,
                    p_data.brand_id AS brand_id,
                    p_data.collection_id AS collection_id,
                    p_data.size_id AS size_id,
                    p_data.qty_incoming AS qty_incoming,
                    p_data.purchase_value AS purchase_value,
                    p_data.qty_outgoing AS qty_outgoing,
                    p_data.retail_value AS retail_value,
                    p_data.qty_balance AS qty_balance,
                    p_data.currency_id AS currency_id,

                    -- 🛠️ MATRIX PRICING SQL SUBQUERY: Extracts price matching BOTH product ID and strict size ID layer
                    COALESCE((
                        SELECT sub_rl.retail_price 
                        FROM cloth_receipt_line sub_rl
                        JOIN cloth_receipt sub_r ON sub_r.id = sub_rl.receipt_id
                        WHERE sub_rl.sku_id = p_data.product_id AND sub_rl.size_id = p_data.size_id AND sub_r.state = 'done'
                        ORDER BY sub_rl.id DESC 
                        LIMIT 1
                    ), 0.00) AS retail_price

                FROM (
                    SELECT 
                        p.id AS product_id,
                        p.sku AS sku,
                        p.brand_id AS brand_id,
                        p.collection_id AS collection_id,
                        -- Size field source target now switched tightly to active lines references index mapping
                        COALESCE(rl.size_id, ol.size_id) AS size_id,

                        COALESCE(SUM(rl.qty), 0) AS qty_incoming,
                        COALESCE(SUM(rl.purchase_subtotal), 0) AS purchase_value,
                        COALESCE(SUM(ol.qty), 0) AS qty_outgoing,
                        COALESCE(SUM(ol.price_subtotal), 0) AS retail_value,
                        (COALESCE(SUM(rl.qty), 0) - COALESCE(SUM(ol.qty), 0)) AS qty_balance,
                        (SELECT id FROM res_currency WHERE name = 'UAH' LIMIT 1) AS currency_id
                    FROM cloth_product p

                    -- 🛠️ MATRIX LEFT JOIN OPERATIONS: Link and evaluate transactions records by matching sizes paths
                    LEFT JOIN cloth_receipt_line rl ON rl.sku_id = p.id AND rl.id IN (
                        SELECT id FROM cloth_receipt_line WHERE receipt_id IN (
                            SELECT id FROM cloth_receipt WHERE state = 'done'
                        )
                    )
                    LEFT JOIN cloth_order_line ol ON ol.product_id = p.id AND ol.size_id = rl.size_id AND ol.id IN (
                        SELECT id FROM cloth_order_line WHERE order_id IN (
                            SELECT id FROM cloth_order WHERE state IN ('shipped', 'received')
                        )
                    )

                    -- Filter out ghost skeleton matrix rows that do not possess any transactional movement history
                    WHERE rl.size_id IS NOT NULL OR ol.size_id IS NOT NULL

                    GROUP BY p.id, p.sku, p.brand_id, p.collection_id, COALESCE(rl.size_id, ol.size_id)
                ) AS p_data
            )
        """)
