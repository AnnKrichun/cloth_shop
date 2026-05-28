{
    "name": "Clothing Shop Management",
    "version": "1.0",
    "category": "Sales",
    "summary": "Professional management system for clothing stores",
    "author": "Ann Krichun",
    "license": "LGPL-3",
    "description": """
Clothing Shop Management Module
===============================
This module provides a comprehensive solution for clothing retail:
* Manage **Brands** and **Collections**.
* Track **Products** with specific sizes and fabric compositions.
* Handle **Customer Orders** with automated calculations.
* Custom **Reports** and **Wizards** for price management.
    """,
    "depends": ["base", "account", "product", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/currency_automation_data.xml",
        "data/ir_sequence_data.xml",
        "views/res_config_settings_views.xml",
        "views/cloth_brand_views.xml",
        "views/cloth_collection_views.xml",
        "views/cloth_markup_views.xml",
        "views/cloth_size_views.xml",
        "views/cloth_product_views.xml",
        "views/cloth_receipt_views.xml",
        "views/cloth_order_views.xml",
        "views/res_partner_views.xml",
        "views/res_currency_views.xml",
        "wizard/recalculate_markup_wizard_view.xml",
        "report/cloth_inventory_report_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "images": ["static/description/main_screenshot.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "_init_cloth_shop_currencies",
}
