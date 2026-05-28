from odoo.exceptions import ValidationError
from odoo.fields import Date
from odoo.tests.common import TransactionCase


class TestClothShopCore(TransactionCase):
    """
    Automated test suite securing structural integrity and business logic
    validation across all newly introduced clothing store models.
    """

    @classmethod
    def setUpClass(cls):
        """Initializes global master data counters and baseline configuration records."""
        super().setUpClass()

        # Setup master records for standalone tables to share across tests
        cls.brand = cls.env["cloth.brand"].create(
            {
                "name": "Test Apex Athlete",
                "country_id": cls.env.ref("base.us").id,
            },
        )
        cls.size = cls.env["cloth.size"].create({"name": "XL"})
        cls.collection = cls.env["cloth.collection"].create(
            {"name": "Winter Warmth 2026"},
        )

    def test_01_cloth_brand_creation(self):
        """Verifies successful database instantiation of independent brand master data records."""
        self.assertEqual(
            self.brand.name, "Test Apex Athlete", "Brand master card name mismatch!",
        )

    def test_02_cloth_size_creation(self):
        """Validates exact string matching upon custom size metadata grid registration."""
        self.assertEqual(self.size.name, "XL", "Size grid record key token mismatch!")

    def test_03_cloth_collection_creation(self):
        """Ensures temporal clothing lineup parameters hold their operational assignments."""
        self.assertEqual(
            self.collection.name,
            "Winter Warmth 2026",
            "Seasonal configuration string tracking flaw!",
        )

    def test_04_cloth_markup_coefficient_evaluation(self):
        """Confirms pricing adjustment matrix rules secure correct relational coefficient metrics."""
        markup = self.env["cloth.markup.coefficient"].create(
            {
                "brand_id": self.brand.id,
                "collection_id": self.collection.id,
                "coefficient": 2.25,
            },
        )
        self.assertAlmostEqual(
            markup.coefficient, 2.25, msg="Financial multiplier matrix precision fault!",
        )

    def test_05_cloth_product_sku_formatting_trigger(self):
        """Validates automated multi-create hook sanitizing and transforming SKU text to uppercase."""
        product = self.env[
            "cloth.product"
        ].create(
            {
                "name": "   hud-apx-test   ",  # String contains explicit spaces and lowercase letters
                "product_title": "Performance Hoodie Pro",
                "brand_id": self.brand.id,
                "collection_id": self.collection.id,
            },
        )
        # The create method from cloth_product.py must clean spaces and convert to UPPERCASE
        self.assertEqual(
            product.name,
            "HUD-APX-TEST",
            "Automated product create hooks skipped text sanitization!",
        )

    def test_06_cloth_product_matrix_generation_logic(self):
        """Validates that product stock breakdown matrix lines generate correctly based on data."""
        # 1. Створюємо новий чистий товар
        product = self.env["cloth.product"].create(
            {
                "name": "TSH-MATRIX-CHECK",
                "product_title": "Matrix Test Tee",
                "brand_id": self.brand.id,
                "collection_id": self.collection.id,
            },
        )

        # 2. Емулюємо надходження товару на склад: створюємо проведену накладну
        receipt = self.env["cloth.receipt"].create(
            {
                "name": "WH/IN/TEST/999",
                "date": Date.today(),
                "state": "done",  # Встановлюємо статус проведено
            },
        )

        # Додаємо лінію надходження з нашим розміром (XL)
        self.env["cloth.receipt.line"].create(
            {
                "receipt_id": receipt.id,
                "sku_id": product.id,
                "size_id": self.size.id,
                "purchase_currency_id": self.env.ref("base.UAH").id,
                "qty": 15,
                "purchase_price": 10.00,
                "retail_price": 15.00,
            },
        )

        # 3. Викликаємо метод генерації ліній матриці (код з вашого файлу cloth_product.py)
        product.action_generate_stock_lines()

        # 4. Перевіряємо, що в картці товару автоматично з'явився РІВНО ОДИН рядок матриці для цього розміру
        self.assertEqual(
            len(product.stock_line_ids),
            1,
            "Product stock matrix failed to generate layout rows!",
        )
        self.assertEqual(
            product.stock_line_ids[0].size_id.id,
            self.size.id,
            "Matrix generated invalid size reference!",
        )

    def test_07_cloth_partner_negative_discount_validation(self):
        """Ensures that personal discount fields strictly reject values outside the 0-100% boundary."""
        partner = self.env["res.partner"].create({"name": "Test Customer"})

        # Negative Testing: Перевіряємо від'ємне значення (-5%) — система має викинути ValidationError
        with self.assertRaises(
            ValidationError,
            msg="System allowed a dangerous negative discount percentage!",
        ):
            partner.write({"personal_discount": -5.0})

        # Negative Testing: Перевіряємо занадто велике значення (120%) — система також має викинути ValidationError
        with self.assertRaises(
            ValidationError, msg="System allowed an invalid discount exceeding 100%!",
        ):
            partner.write({"personal_discount": 120.0})

    def test_08_cloth_receipt_zero_retail_price_validation(self):
        """Validates that warehouse receipts cannot be validated if any lines hold zero or negative prices."""
        # Створюємо чернетку накладної
        receipt = self.env["cloth.receipt"].create(
            {
                "name": "WH/IN/TEST/001",
                "date": Date.today(),
            },
        )

        # Додаємо лінію з примусово нульовою роздрібною ціною (retail_price = 0.00)
        self.env["cloth.receipt.line"].create(
            {
                "receipt_id": receipt.id,
                "sku_id": self.env["cloth.product"]
                .create(
                    {
                        "name": "TSH-ZERO-PRICE",
                        "product_title": "Zero Price Tee",
                        "brand_id": self.brand.id,
                        "collection_id": self.collection.id,
                    },
                )
                .id,
                "size_id": self.size.id,
                "purchase_currency_id": self.env.ref("base.UAH").id,
                "qty": 10,
                "purchase_price": 10.00,
                "retail_price": 0.00,  # Клінічний нуль
            },
        )

        # Спроба провести таку накладну має миттєво викликати ValidationError
        with self.assertRaises(
            ValidationError,
            msg="Warehouse allowed a zero retail price validation log event!",
        ):
            receipt.action_button_validate()
