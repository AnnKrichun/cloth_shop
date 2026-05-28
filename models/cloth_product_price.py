# -*- coding: utf-8 -*-
from odoo import fields, models


class ClothProductPrice(models.Model):
    """
    Price matrix model to store computed retail prices
    individually for each Product and Size combination.
    """

    _name = "cloth.product.price"
    _description = "Product Variant Retail Prices"
    _rec_name = "retail_price"

    # Relational link fields to core models
    product_id = fields.Many2one(
        "cloth.product",
        string="Product",
        required=True,
        ondelete="cascade",
    )
    size_id = fields.Many2one(
        "cloth.size",
        string="Size",
        required=True,
        ondelete="cascade",
    )

    # Store calculated active retail price label value
    retail_price = fields.Float(
        string="Retail Price",
        required=True,
        digits=(12, 2),
        default=0.00,
    )

    # Database constraint rule preventing duplicates for the same item size combination
    _sql_constraints = [
        (
            "product_size_price_unique",
            "unique(product_id, size_id)",
            "The retail price for this specific product variant already exists!",
        ),
    ]
