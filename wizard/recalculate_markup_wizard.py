# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RecalculateMarkupWizard(models.TransientModel):
    """
    Transient model wizard designed for mass retail price recalculation
    utilizing weighted average cost (AVCO) matrix metrics.
    """

    _name = "cloth.recalculate.markup.wizard"
    _description = "Mass AVCO Price Recalculation Wizard"

    brand_id = fields.Many2one(
        "cloth.brand",
        string="Brand",
        required=True,
        help="Select a brand to trigger inventory valuation and price update",
    )

    @api.model
    def default_get(self, fields_list):
        """⚡ АВТОПОДСТАНОВКА ДЛЯ ODOO 19: Вычитывает бренд из активной строки матрицы наценок"""
        res = super(RecalculateMarkupWizard, self).default_get(fields_list)

        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")

        if active_model == "cloth.markup.coefficient" and active_id:
            # Находим строку матрицы наценок, на которой кликнули
            markup_line = self.env["cloth.markup.coefficient"].browse(active_id)
            if markup_line.exists() and markup_line.brand_id:
                res["brand_id"] = markup_line.brand_id.id

        return res

    def action_recalculate(self):
        """
        Calculates the weighted average cost price for each variant layer
        and populates the cloth.product.price relational database matrix.
        """
        # Find all operational product templates linked to the targeted brand layer
        products = self.env["cloth.product"].search(
            [("brand_id", "=", self.brand_id.id)]
        )
        if not products:
            raise UserError(_("No products found for the selected brand!"))

        updated_count = 0

        for product in products:
            # ⚡ ФИКС НАЦЕНКИ: Ищем живое правило коэффициента для связки конкретного Бренда и Коллекции товара
            rule = self.env["cloth.markup.coefficient"].search(
                [
                    ("brand_id", "=", product.brand_id.id),
                    ("collection_id", "=", product.collection_id.id),
                ],
                limit=1,
            )
            # Если специфическое правило не найдено, берем дефолт 1.5
            markup_coefficient = rule.coefficient if rule else 1.5

            # Aggregate receipt line statistics for specific item configuration profiles
            receipt_lines = self.env["cloth.receipt.line"].search(
                [("sku_id", "=", product.id), ("receipt_id.state", "=", "done")]
            )

            if not receipt_lines:
                continue

            # Group cost analytics directly by sizes to secure granular AVCO calculation
            sizes_in_receipts = receipt_lines.mapped("size_id")

            for size in sizes_in_receipts:
                variant_lines = receipt_lines.filtered(
                    lambda l: l.size_id.id == size.id
                )

                # Complex business logic execution: Weighted average computation layer
                total_qty = sum(line.qty for line in variant_lines)
                total_amount = sum(
                    (line.purchase_price * line.qty) for line in variant_lines
                )

                if total_qty > 0:
                    weighted_average_cost = total_amount / total_qty
                    new_retail_price = weighted_average_cost * markup_coefficient

                    # Check for an existing price log matrix row or instantiate a clean record
                    price_record = self.env["cloth.product.price"].search(
                        [("product_id", "=", product.id), ("size_id", "=", size.id)],
                        limit=1,
                    )

                    if price_record:
                        price_record.write({"retail_price": new_retail_price})
                    else:
                        self.env["cloth.product.price"].create(
                            {
                                "product_id": product.id,
                                "size_id": size.id,
                                "retail_price": new_retail_price,
                            }
                        )
                    updated_count += 1

        # Return a standardized notification popup layout execution token
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("AVCO Recalculation Complete"),
                "message": _(
                    "Successfully synchronized and updated %s price configurations for brand %s."
                )
                % (updated_count, self.brand_id.name),
                "type": "success",
                "sticky": False,
            },
        }
