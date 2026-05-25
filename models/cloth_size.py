# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class ClothSize(models.Model):
    """
    Model representing clothing size parameters with strict inventory validation.
    """

    _name = "cloth.size"
    _description = "Clothing Sizes"
    _order = "sequence, name"

    # Dimensional code identifier (e.g., 'XS', 'S', 'M', 'L', 'XL')
    name = fields.Char(string="Size Chart", required=True, index=True)

    sequence = fields.Integer(string="Sequence Order", default=10)

    def unlink(self):
        """
        Prevents the deletion of a size record if it is actively assigned to any product.

        Queries the cloth.product registry to enforce strict data integrity rules.
        """
        for size in self:
            # Check if there are any products referencing this specific size ID
            product_count = self.env["cloth.product"].search_count(
                [("size_id", "=", size.id)]
            )

            if product_count > 0:
                # Block the deletion pipeline and throw a user-facing security notification
                raise UserError(
                    _(
                        "You cannot delete the size '%s' because it is currently linked to %s active product(s)!"
                    )
                    % (size.name, product_count)
                )

        return super().unlink()
