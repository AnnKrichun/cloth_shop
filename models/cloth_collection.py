# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ClothCollection(models.Model):
    """
    Model representing fashion and seasonal clothing collections.

    Tracks designer release themes, execution years, and seasonal
    parameters to segregate products in retail catalogs.
    """

    _name = "cloth.collection"
    _description = "Clothing Collections"
    _order = "year desc, season"

    # The title or main design topic of the fashion line (e.g. 'Denim', 'Urban')
    name = fields.Char(string="Collection Theme", required=True)

    # Calendar year of the collection release, defaults to the current year
    year = fields.Char(
        string="Year", required=True, default=lambda self: str(fields.Date.today().year)
    )

    # Seasonal classification partition parameters
    season = fields.Selection(
        [("spring_summer", "Spring / Summer"), ("autumn_winter", "Autumn / Winter")],
        string="Season",
        required=True,
        default="spring_summer",
    )

    @api.depends("year", "season", "name")
    def _compute_display_name(self):
        """
        Computes the standard user-facing name representation for lookup panels.

        Odoo 19 native mechanism replacing deprecated name_get().
        Formats the visual output as: [Year] Season Label - Collection Theme.
        """
        for rec in self:
            # Safely fetch the human-readable string translation from the selection mapping matrix
            season_label = dict(self._fields["season"].selection).get(rec.season, "")
            rec.display_name = f"[{rec.year}] {season_label} - {rec.name}"
