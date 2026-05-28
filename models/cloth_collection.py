from odoo import api, fields, models


class ClothCollection(models.Model):
    """
    Model for storing clothing collections.
    Tracks fashion themes, years, and seasons to organize products.
    """

    _name = "cloth.collection"
    _description = "Clothing Collections"
    _order = "year desc, season"

    # The title or name of the collection (e.g., 'Urban Breeze')
    name = fields.Char(string="Collection Theme", required=True)

    # Execution year, defaults to the current year automatically
    year = fields.Char(
        string="Year",
        required=True,
        default=lambda self: str(fields.Date.today().year),
    )

    # Seasonal choice filter for apparel separation
    season = fields.Selection(
        [("spring_summer", "Spring / Summer"), ("autumn_winter", "Autumn / Winter")],
        string="Season",
        required=True,
        default="spring_summer",
    )

    @api.depends("year", "season", "name")
    def _compute_display_name(self):
        """
        Computes how the collection looks in selection fields.
        Formats the output text as: [Year] Season - Theme Name.
        """
        for rec in self:
            # COMMENT: We read the selection dictionary to get the nice text label
            # (like 'Spring / Summer') instead of the technical database key.
            season_label = dict(self._fields["season"].selection).get(rec.season, "")

            # Setting the final readable name for lookup panels
            rec.display_name = f"[{rec.year}] {season_label} - {rec.name}"
