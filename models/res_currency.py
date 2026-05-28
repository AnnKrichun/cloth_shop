# -*- coding: utf-8 -*-
import logging
import requests

from odoo import api, fields, models

# Logger for banking synchronization logs tracking
_logger = logging.getLogger(__name__)


class ResCurrency(models.Model):
    """
    Extends core res.currency model to add PrivatBank API sync engine.
    """

    _inherit = "res.currency"

    @api.model
    def _update_privatbank_currency_rates(self):
        """
        Fetches live commercial currency rates directly from the PrivatBank API.
        Calculates universal cross-rates for standard base currencies.
        """
        # Active official PrivatBank commercial endpoint URL
        url = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"

        _logger.info("PRIVATBANK SYNC STARTED: Sending request to URL %s", url)
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                _logger.warning(
                    "PrivatBank API endpoint is unavailable. HTTP Status: %s",
                    response.status_code,
                )
                return

            data = response.json()
            company = self.env.company
            base_currency_name = (
                company.currency_id.name
            )  # Active company currency (e.g., UAH)
            today_date = fields.Date.today()

            # Baseline dictionary mapping banking parameters matching standard keys
            rates_in_uah = {
                "UAH": 1.0,
                "USD": 0.0,
                "EUR": 0.0,
            }

            for rate_data in data:
                ccy = rate_data.get("ccy")
                sale_rate = float(rate_data.get("sale", 0.0))
                if ccy in ["USD", "EUR"] and sale_rate > 0:
                    rates_in_uah[ccy] = sale_rate

            # Run cross-rate calculation formula if both core records are found
            if rates_in_uah["USD"] > 0 and rates_in_uah["EUR"] > 0:
                if base_currency_name in rates_in_uah:
                    base_in_uah = rates_in_uah[base_currency_name]
                else:
                    _logger.warning(
                        "Base currency %s is outside standard pool. Defaulting to USD.",
                        base_currency_name,
                    )
                    base_in_uah = rates_in_uah["USD"]

                _logger.info(
                    "PRIVATBANK SYNC: Multi-currency matrix loaded. Base anchor: %s (Value in UAH: %s)",
                    base_currency_name,
                    base_in_uah,
                )

                # Loop through standard active records and calculate dynamic multipliers factors
                for target_ccy in ["UAH", "USD", "EUR"]:
                    if rates_in_uah[target_ccy] > 0:
                        currency = self.search(
                            [("name", "=", target_ccy), ("active", "=", True)],
                            limit=1,
                        )
                        if currency:
                            # THE UNIVERSAL FORMULA: base currency value in UAH divided by target value in UAH
                            universal_odoo_rate = base_in_uah / rates_in_uah[target_ccy]

                            # Calls the sub-method helper to store or overwrite database data rows
                            self._create_or_update_rate(
                                currency.id,
                                today_date,
                                universal_odoo_rate,
                                company.id,
                            )
                            _logger.info(
                                "Universal factor written for %s relative to %s anchor: %s",
                                target_ccy,
                                base_currency_name,
                                universal_odoo_rate,
                            )

                _logger.info(
                    "PrivatBank cross-rate matrices successfully generated for the active session.",
                )

        except Exception as e:
            _logger.error(
                "Failed to automatically synchronize currency exchange rates from PrivatBank API: %s",
                str(e),
            )

    def _create_or_update_rate(self, currency_id, date, rate_value, company_id):
        """
        Helper method to create a new exchange rate row or overwrite an existing one.
        """
        existing = self.env["res.currency.rate"].search(
            [
                ("currency_id", "=", currency_id),
                ("name", "=", date),
                ("company_id", "=", company_id),
            ],
            limit=1,
        )

        if not existing:
            self.env["res.currency.rate"].create(
                {
                    "currency_id": currency_id,
                    "name": date,
                    "rate": rate_value,
                    "company_id": company_id,
                    "is_privatbank_rate": True,
                },
            )
        else:
            existing.write(
                {
                    "rate": rate_value,
                    "is_privatbank_rate": True,
                },
            )
            _logger.info(
                "Direct database log overwrite executed for currency ID %s on date %s",
                currency_id,
                date,
            )


# ⚡ FIX: Shifted left to the root level to become a standalone core class extension
class ResCurrencyRate(models.Model):
    """
    Extends core exchange lines ledger model to add custom tracking flags.
    """

    _inherit = "res.currency.rate"

    # Custom field tracking application sync metadata layers
    is_privatbank_rate = fields.Boolean(
        string="PrivatBank Rate",
        default=False,
        help="Identifies if this currency rate entry was pulled via PrivatBank commercial API.",
    )
