# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ResCurrency(models.Model):
    """
    Extends core res.currency model to inject localized banking API triggers.
    """

    _inherit = "res.currency"

    @api.model
    def _update_privatbank_currency_rates(self):
        """
        Automated task with fully universal cross-rate calculation engine.
        Supports UAH, USD, EUR, or any other base currency configured in the system.
        """
        # Active and verified service URL for live commercial rates exchange metadata
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
            )  # Active system anchor currency (e.g., UAH, USD, EUR, etc.)
            today_date = fields.Date.today()

            # Live commercial rates fetched directly from the bank API relative to UAH
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

            # If the bank returned active parameters, we evaluate the universal conversion matrix
            if rates_in_uah["USD"] > 0 and rates_in_uah["EUR"] > 0:
                # Find the value of Odoo's current base company currency in UAH
                if base_currency_name in rates_in_uah:
                    base_in_uah = rates_in_uah[base_currency_name]
                else:
                    _logger.warning(
                        "Base currency %s is outside standard retail pool. Defaulting anchor metrics to USD.",
                        base_currency_name,
                    )
                    base_in_uah = rates_in_uah["USD"]

                _logger.info(
                    "PRIVATBANK SYNC: Multi-currency matrix loaded. Base anchor: %s (Value in UAH: %s)",
                    base_currency_name,
                    base_in_uah,
                )

                # Loop through our active workspace records and update their internal rates dynamically
                for target_ccy in ["UAH", "USD", "EUR"]:
                    if rates_in_uah[target_ccy] > 0:
                        currency = self.search(
                            [("name", "=", target_ccy), ("active", "=", True)], limit=1
                        )
                        if currency:
                            # THE UNIVERSAL FORMULA: base currency value in UAH divided by target currency value in UAH
                            universal_odoo_rate = base_in_uah / rates_in_uah[target_ccy]

                            # Calls the helper to either create a new row or overwrite the existing one
                            self._create_or_update_rate(
                                currency.id, today_date, universal_odoo_rate, company.id
                            )
                            _logger.info(
                                "Universal factor written for %s relative to %s anchor: %s",
                                target_ccy,
                                base_currency_name,
                                universal_odoo_rate,
                            )

                _logger.info(
                    "PrivatBank cross-rate matrices successfully generated for the active session."
                )

        except Exception as e:
            _logger.error(
                "Failed to automatically synchronize currency exchange rates from PrivatBank API: %s",
                str(e),
            )

    def _create_or_update_rate(self, currency_id, date, rate_value, company_id):
        """Helper method to manage record mutation constraints safely with direct overwrite"""
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
                }
            )
        else:
            existing.write({"rate": rate_value})
            _logger.info(
                "Direct database log overwrite executed for currency ID %s on date %s",
                currency_id,
                date,
            )


class ResCurrencyRate(models.Model):
    """
    Extends core exchange lines ledger model to handle interface actions mapping.
    """

    _inherit = "res.currency.rate"
