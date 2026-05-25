# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClothMarkupCoefficient(models.Model):
    """
    Model managing pricing rules and profit margin multipliers.

    Combines brand classifications and seasonal collections to dynamically
    evaluate retail market valuation factors across incoming stock invoices.
    """

    _name = "cloth.markup.coefficient"
    _description = "Pricing Markup Coefficients"
    _rec_name = "coefficient"

    # Relational foreign key mapping to the manufacturer brand catalog
    brand_id = fields.Many2one(
        "cloth.brand", string="Brand", required=True, ondelete="cascade"
    )

    # Relational foreign key mapping to the seasonal designer release catalog
    collection_id = fields.Many2one(
        "cloth.collection", string="Collection", required=True, ondelete="cascade"
    )

    # Multiplier ratio used to calculate consumer retail tags from purchase cost
    coefficient = fields.Float(
        string="Markup Multiplier", required=True, default=1.0, digits=(12, 2)
    )

    # Database SQL constraint preventing duplicate pricing parameters for the same matrix intersection
    _brand_collection_unique = models.Constraint(
        "unique(brand_id, collection_id)",
        "A pricing multiplier rule has already been registered for this specific brand and collection combination!",
    )

    @api.constrains("coefficient")
    def _check_coefficient(self):
        """
        Validates that the entered multiplier factor remains financially profitable.

        Enforces a strict operational boundary rule where the ratio cannot be less or equal to zero.
        """
        for rec in self:
            if rec.coefficient <= 0:
                raise ValidationError(
                    _("The markup multiplier coefficient value must be greater than 0!")
                )
