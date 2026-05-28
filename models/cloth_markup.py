# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ClothMarkupCoefficient(models.Model):
    """
    Model for managing pricing markup coefficients.
    Combines brand and collection to calculate retail prices.
    """

    _name = "cloth.markup.coefficient"
    _description = "Pricing Markup Coefficients"

    _rec_names_search = ["brand_id", "collection_id"]

    # Links to core configurations models
    brand_id = fields.Many2one(
        "cloth.brand",
        string="Brand",
        required=True,
        ondelete="cascade",
    )

    collection_id = fields.Many2one(
        "cloth.collection",
        string="Collection",
        required=True,
        ondelete="cascade",
    )

    # Multiplier price value (e.g., 1.5 means +50% markup)
    coefficient = fields.Float(
        string="Markup Multiplier",
        required=True,
        default=1.0,
        digits=(12, 2),
    )

    # Core database index enforcing uniqueness rules
    _sql_constraints = [
        (
            "brand_collection_unique",
            "unique(brand_id, collection_id)",
            "A pricing multiplier rule has already been registered for this specific brand and collection combination!",
        ),
    ]

    @api.depends("brand_id", "collection_id", "coefficient")
    def _compute_display_name(self):
        """
        Computes how the markup rule looks in lookup fields.
        Formats as: Brand Name - Collection Name (xMultiplier).
        """
        for rec in self:
            if rec.brand_id and rec.collection_id:
                rec.display_name = f"{rec.brand_id.name} - {rec.collection_id.name} (x{rec.coefficient})"
            else:
                # COMMENT: Wrapped text in _() to allow translation support in UI
                rec.display_name = _("Markup Rule #%s") % (rec.id or _("New"))

    @api.constrains("coefficient")
    def _check_coefficient(self):
        """
        Validation code preventing wrong multiplier input.
        The system blocks coefficients equal to or less than zero.
        """
        for rec in self:
            # COMMENT: Business logic validation check
            if rec.coefficient <= 0:
                raise ValidationError(
                    _(
                        "The markup multiplier coefficient value must be greater than 0!"
                    ),
                )
