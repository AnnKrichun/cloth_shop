# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    """
    Extends core res.company model to inject global financial configuration
    parameters for store-wide markup rules.
    """

    _inherit = "res.company"

    # Global backup markup value if specific coefficients rules are missing
    default_markup_coef = fields.Float(
        string="Global Markup Coefficient",
        default=1.2,
        help="Fallback pricing multiplier used when specific Brand and Collection markup rules are missing.",
    )
