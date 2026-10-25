from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Company, Module, ModuleSetting, Partner
from core.settings_schema import current_values, save_values
from core.services import ModuleDependencyError, set_module
from inventory.models import Product, Warehouse
from inventory.services import StockError, issue, receive, on_hand
from sales.models import SalesLine, SalesOrder
from sales.services import deliver
from core.management.commands.seed_modules import Command as SeedModules


class ModuleRulesTests(TestCase):
    def setUp(self):
        SeedModules().handle()
        self.company = Company.objects.create(name="شركة اختبار", code="TEST")

    def test_cannot_enable_module_without_dependency(self):
        crm = Module.objects.get(code="crm")
        with self.assertRaises(ModuleDependencyError):
            set_module(self.company, crm, True)

    def test_cannot_disable_module_that_others_need(self):
        set_module(self.company, Module.objects.get(code="contacts"), True)
        set_module(self.company, Module.objects.get(code="crm"), True)
        with self.assertRaises(ModuleDependencyError):
            set_module(self.company, Module.objects.get(code="contacts"), False)

    def test_user_access_requires_company_module_and_permission(self):
        User = get_user_model()
        user = User.objects.create_user(username="u1", company=self.company)
        self.assertFalse(user.can_access("inventory"))
        set_module(self.company, Module.objects.get(code="inventory"), True)
        self.assertFalse(user.can_access("inventory"))  # مش مسموحله
        user.allowed_modules.add(Module.objects.get(code="inventory"))
        self.assertTrue(user.can_access("inventory"))


class StockLedgerTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="شركة اختبار", code="TST2")
        self.wh = Warehouse.objects.create(company=self.company, code="M", name="رئيسي")
        self.prod = Product.objects.create(company=self.company, code="A", name="صنف أ")

    def test_balance_is_sum_of_moves(self):
        receive(company=self.company, product=self.prod, warehouse=self.wh, qty=10)
        issue(company=self.company, product=self.prod, warehouse=self.wh, qty=4)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("6"))

    def test_negative_stock_is_blocked(self):
        receive(company=self.company, product=self.prod, warehouse=self.wh, qty=2)
        with self.assertRaises(StockError):
            issue(company=self.company, product=self.prod, warehouse=self.wh, qty=5)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("2"))

    def test_delivery_is_all_or_nothing(self):
        other = Product.objects.create(company=self.company, code="B", name="صنف ب")
        receive(company=self.company, product=self.prod, warehouse=self.wh, qty=10)
        receive(company=self.company, product=other, warehouse=self.wh, qty=1)
        customer = Partner.objects.create(company=self.company, name="عميل")
        order = SalesOrder.objects.create(company=self.company, number="SO-1", customer=customer)
        SalesLine.objects.create(order=order, product=self.prod, qty=3, price=10)
        SalesLine.objects.create(order=order, product=other, qty=5, price=10)  # الرصيد مش كافي
        with self.assertRaises(StockError):
            deliver(order, self.wh)
        # مفيش حاجة اتصرفت لأن التسليم كله اترجع
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")



class ModuleSettingsSchemaTests(TestCase):
    def setUp(self):
        SeedModules().handle()
        self.company = Company.objects.create(name="شركة إعدادات", code="SETTINGS")

    def test_settings_round_trip_uses_module_foreign_key_and_json_values(self):
        values_to_save = {
            "prefix": "SOX",
            "approval": False,
            "quote_validity": 45,
            "tax_rate": Decimal("15.25"),
        }

        save_values(self.company, "sales", values_to_save)

        sales_module = Module.objects.get(code="sales")
        stored = {
            row.key: row.value
            for row in ModuleSetting.objects.filter(company=self.company, module=sales_module)
        }
        self.assertEqual(stored["prefix"], "SOX")
        self.assertIs(stored["approval"], False)
        self.assertEqual(stored["quote_validity"], 45)
        self.assertEqual(stored["tax_rate"], "15.25")

        restored = current_values(self.company, "sales")
        self.assertEqual(restored["prefix"], "SOX")
        self.assertIs(restored["approval"], False)
        self.assertEqual(restored["quote_validity"], 45)
        self.assertEqual(restored["tax_rate"], Decimal("15.25"))

    def test_false_setting_is_preserved_and_defaults_are_company_scoped(self):
        save_values(self.company, "sales", {"approval": False})
        other_company = Company.objects.create(name="شركة أخرى", code="SETTINGS2")

        self.assertIs(current_values(self.company, "sales")["approval"], False)
        self.assertIs(current_values(other_company, "sales")["approval"], True)
