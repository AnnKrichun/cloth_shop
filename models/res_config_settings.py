from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """
    Extends system config parameters matrix to expose store retail settings
    using completely independent core system configuration parameters dictionary wrappers.
    """

    _inherit = "res.config.settings"

    # Fully autonomous independent Many2one pointer fallback field
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

        # Pull key parameter from system settings parameters table storage registry
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

        # Write data record directly into system configuration parameters table entries
        if self.retail_currency_id:
            self.env["ir.config_parameter"].sudo().set_param(
                "cloth_shop.retail_currency_id", self.retail_currency_id.id,
            )

    def action_cloth_shop_update_rates_now(self):
        """
        Triggered manually by the supervisor inside Settings layout panel.
        Forces backend to fire the core PrivatBank API sync pipeline immediately
        in the context of current company and explicitly commits the changes.
        """
        # Execute synchronization using the current active company context environment
        self.env["res.currency"].with_company(
            self.env.company,
        )._update_privatbank_currency_rates()

        # Force flush and commit the transaction to ensure live entries are saved immediately
        self.env.cr.commit()
        return True
