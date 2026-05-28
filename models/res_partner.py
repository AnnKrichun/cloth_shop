# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """
    Extends core res.partner model to inject a localized personal discount
    field used across customer order calculation matrices.
    """

    _inherit = "res.partner"

    # Customer discount percent linked directly to orders formula
    personal_discount = fields.Float(
        string="Personal Discount (%)",
        default=0.0,
    )

    @api.constrains("personal_discount")
    def _check_discount(self):
        """
        Validates that the personal discount value remains between 0% and 100%.
        """
        for partner in self:
            # COMMENT: Checks if input discount meets standard business rules boundaries
            if partner.personal_discount < 0 or partner.personal_discount > 100:
                raise ValidationError(
                    _("Personal discount must be between 0 and 100%!")
                )
