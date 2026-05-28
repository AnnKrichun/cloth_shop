import contextlib

# 1. SYSTEM MODEL INTEGRATION ROUTING
from odoo import SUPERUSER_ID, api, fields

from . import models, report, wizard


# 2. SEED DATA CURRENCY INITIALIZATION HOOK (POST-INIT HOOK)
def _init_cloth_shop_currencies(env):
    """
    POST-INIT HOOK: Automatically executed during module installation.
    1. Activates code profiles for USD, EUR, and UAH in the core registry.
    2. Instantly assigns UAH as the official Store Retail Currency inside parameters table.
    3. Fetches live commercial currency exchange rates from PrivatBank API.
    """
    # Step A: Force activate core trade currency records inside system directory
    currencies = env["res.currency"].search([("name", "in", ["USD", "UAH", "EUR"])])
    if currencies:
        currencies.write({"active": True})

    # Step B: MANDATORY ASSIGNMENT — Set UAH as the default Retail Currency for the module
    uah_currency = env["res.currency"].search([("name", "=", "UAH")], limit=1)
    if uah_currency:
        # Dynamically inject the currency ID parameter before Odoo starts reading XML demo files
        env["ir.config_parameter"].sudo().set_param(
            "cloth_shop.retail_currency_id",
            uah_currency.id,
        )

    # Step C: Pre-load fresh currency exchange rate factors directly from PrivatBank API
    with contextlib.suppress(Exception):
        env["res.currency"]._update_privatbank_currency_rates()
