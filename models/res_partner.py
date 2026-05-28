from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    personal_discount = fields.Float(
        string='Персональна знижка (%)',
        default=0.0,
    )

    @api.constrains('personal_discount')
    def _check_discount(self):
        for partner in self:
            if partner.personal_discount < 0 or partner.personal_discount > 100:
                raise ValidationError(_("Персональна знижка має бути в межах від 0 до 100%!"))
