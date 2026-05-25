from odoo import models, fields


class ClothBrand(models.Model):
    """
    Model representing clothing manufacturing brands.

    Tracks the brand identity, its geographic origin country,
    and store logo for retail representation.
    """

    _name = "cloth.brand"
    _description = "Clothing Brands"
    _order = "name"

    # Brand text identifier (e.g. 'Zara', 'Nike')
    name = fields.Char(string="Brand Name", required=True, index=True)

    # Relational foreign key linking to the Odoo global countries directory (res.country model)
    country_id = fields.Many2one("res.country", string="Country of Origin")

    # Binary storage for image uploads, kept as DB attachment for better scale performance
    logo = fields.Binary(string="Logo", attachment=True)
