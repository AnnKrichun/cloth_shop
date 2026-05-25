from odoo import models, fields


class ClothRecalculateMarkupWizard(models.TransientModel):
    _name = "cloth.recalculate.markup.wizard"
    _description = "Тимчасова модель масової націнки"

    new_coefficient = fields.Float(
        string="Груповий коефіцієнт націнки", required=True, default=1.5
    )

    def action_apply_markup(self):
        active_id = self.env.context.get("active_id")
        if active_id:
            receipt = self.env["cloth.receipt"].browse(active_id)
            for line in receipt.line_ids:
                line.retail_price = line.purchase_price * self.new_coefficient
