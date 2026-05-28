from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ClothMarkupCoefficient(models.Model):
    """
    Model managing pricing rules and profit margin multipliers.

    Combines brand classifications and seasonal collections to dynamically
    evaluate retail market valuation factors across incoming stock invoices.
    """

    _name = "cloth.markup.coefficient"
    _description = "Pricing Markup Coefficients"

    # В Odoo 19 замість _rec_name краще перевизначати _compute_display_name для красивого вигляду в інтерфейсі
    _rec_names_search = ["brand_id", "collection_id"]

    # Relational foreign key mapping to the manufacturer brand catalog
    brand_id = fields.Many2one(
        "cloth.brand", string="Brand", required=True, ondelete="cascade",
    )

    # Relational foreign key mapping to the seasonal designer release catalog
    collection_id = fields.Many2one(
        "cloth.collection", string="Collection", required=True, ondelete="cascade",
    )

    # Multiplier ratio used to calculate consumer retail tags from purchase cost
    coefficient = fields.Float(
        string="Markup Multiplier", required=True, default=1.0, digits=(12, 2),
    )

    # ФІКС: Правильний синтаксис для унікальних обмежень на рівні PostgreSQL
    _sql_constraints = [
        (
            "brand_collection_unique",
            "unique(brand_id, collection_id)",
            "A pricing multiplier rule has already been registered for this specific brand and collection combination!",
        ),
    ]

    @api.depends("brand_id", "collection_id", "coefficient")
    def _compute_display_name(self):
        """Формує красиву та зрозумілу назву для пошуку та хлібних крихт (UX фікс)."""
        for rec in self:
            if rec.brand_id and rec.collection_id:
                rec.display_name = f"{rec.brand_id.name} - {rec.collection_id.name} (x{rec.coefficient})"
            else:
                rec.display_name = f"Markup Rule #{rec.id or 'New'}"

    @api.constrains("coefficient")
    def _check_coefficient(self):
        """
        Validates that the entered multiplier factor remains financially profitable.

        Enforces a strict operational boundary rule where the ratio cannot be less or equal to zero.
        """
        for rec in self:
            if rec.coefficient <= 0:
                raise ValidationError(
                    _("The markup multiplier coefficient value must be greater than 0!"),
                )
