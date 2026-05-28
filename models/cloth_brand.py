from odoo import fields, models


class ClothBrand(models.Model):
    """
    Model for storing clothing brands.
    Keeps information about brand name, country, and logo.
    """

    _name = "cloth.brand"
    _description = "Clothing Brands"
    _order = "name"

    # Main brand name field (indexed for faster search)
    name = fields.Char(string="Brand Name", required=True, index=True)

    # Link to the standard country model in Odoo
    country_id = fields.Many2one("res.country", string="Country of Origin")

    # Brand image file.
    # COMMENT: attachment=True saves the image file into the Odoo storage folder
    # instead of the database, to keep the database fast and small.
    logo = fields.Binary(string="Logo", attachment=True)
