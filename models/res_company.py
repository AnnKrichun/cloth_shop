from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    default_markup_coef = fields.Float(
        string='Глобальний коефіцієнт націнки',
        default=1.2,
        help="Використовується, якщо для Бренду та Колекції не задано індивідуальну націнку"
    )
