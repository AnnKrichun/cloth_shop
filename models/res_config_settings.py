# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """
    Extends system config parameters matrix to expose store retail settings.
    """

    _inherit = "res.config.settings"

    # Main retail currency parameter linked to the store
    retail_currency_id = fields.Many2one(
        "res.currency",
        string="Store Retail Currency",
        help="Global pricing currency used across all customer retail checkout sales operations.",
    )

    @api.model
    def get_values(self):
        """
        Natively pulls the stored operational currency parameter directly
        from the system database settings parameters register registry.
        """
        res = super().get_values()

        # COMMENT: Read the currency field value from the core system parameters table
        stored_currency_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cloth_shop.retail_currency_id")
        )

        res.update(
            retail_currency_id=int(stored_currency_id)
            if stored_currency_id
            else self.env.company.currency_id.id,
        )
        return res

    def set_values(self):
        """
        Natively flushes the settings currency directly into ir.config_parameter tables.
        """
        super().set_values()

        # COMMENT: Write the chosen currency ID directly into ir.config_parameter database table
        if self.retail_currency_id:
            self.env["ir.config_parameter"].sudo().set_param(
                "cloth_shop.retail_currency_id",
                self.retail_currency_id.id,
            )

    def action_cloth_shop_update_rates_now(self):
        """
        Forces backend to fire the core PrivatBank API sync pipeline immediately.
        """
        # COMMENT: Run manual exchange rate sync using current active company context
        self.env["res.currency"].with_company(
            self.env.company,
        )._update_privatbank_currency_rates()

        # COMMENT: Force immediate database commit to make updates visible right now
        self.env.cr.commit()
        return True
