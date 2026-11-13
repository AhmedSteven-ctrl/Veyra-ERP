"""اختبارات سير الأوامر (تأكيد/تسليم/استلام)، متوسط التكلفة، الباركود، الإعدادات، وتغيير كلمة المرور."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.management.commands.seed_modules import Command as SeedModules
from core.models import Company, CompanyModule, Module, Partner
from core.settings_schema import current_values, save_values
from core.views import _next_number
from inventory.forms import ProductForm
from inventory.models import Product, Warehouse
from inventory.services import StockError, on_hand, receive
from purchasing.forms import PurchaseLineForm
from purchasing.models import PurchaseLine, PurchaseOrder
from purchasing.services import confirm_order as confirm_purchase
from purchasing.services import receive_order
from sales.forms import SalesLineForm
from sales.models import SalesLine, SalesOrder
from sales.services import confirm_order as confirm_sale
from sales.services import deliver


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="شركة سير", code="FLOW")
        self.wh = Warehouse.objects.create(company=self.company, code="M", name="رئيسي")
        self.prod = Product.objects.create(company=self.company, code="P1", name="صنف", sale_price=Decimal("100"))
        self.customer = Partner.objects.create(company=self.company, name="عميل", kind="customer")
        self.supplier = Partner.objects.create(company=self.company, name="مورد", kind="supplier")
        receive(company=self.company, product=self.prod, warehouse=self.wh, qty=10)

    def _sale(self, number="SO-1", status="confirmed", qty=2):
        order = SalesOrder.objects.create(company=self.company, number=number, customer=self.customer, status=status)
        SalesLine.objects.create(order=order, product=self.prod, qty=qty, price=100)
        return order

    def _purchase(self, number, product, qty, cost, status="confirmed"):
        order = PurchaseOrder.objects.create(company=self.company, number=number, supplier=self.supplier, status=status)
        PurchaseLine.objects.create(order=order, product=product, qty=qty, cost=cost)
        return order

    # ---------- المبيعات ----------
    def test_draft_must_be_confirmed_before_delivery(self):
        order = self._sale(status="draft")
        with self.assertRaises(ValueError):
            deliver(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))
        confirm_sale(order)
        deliver(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("8"))
        self.assertEqual(order.status, "delivered")

    def test_delivery_cannot_run_twice(self):
        order = self._sale()
        deliver(order, self.wh)
        with self.assertRaises(ValueError):
            deliver(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("8"))

    def test_double_click_with_stale_copy_cannot_deliver_twice(self):
        order = self._sale()
        first = SalesOrder.objects.get(pk=order.pk)
        second = SalesOrder.objects.get(pk=order.pk)  # نسخة قديمة لسه شايفة الأمر "مؤكد"
        deliver(first, self.wh)
        with self.assertRaises(ValueError):
            deliver(second, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("8"))

    def test_empty_order_cannot_be_confirmed_or_delivered(self):
        draft = SalesOrder.objects.create(company=self.company, number="SO-E1", customer=self.customer, status="draft")
        with self.assertRaises(ValueError):
            confirm_sale(draft)
        confirmed = SalesOrder.objects.create(company=self.company, number="SO-E2", customer=self.customer)
        with self.assertRaises(ValueError):
            deliver(confirmed, self.wh)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, "confirmed")  # التسليم الفاشل اترجع

    def test_delivery_needs_a_warehouse(self):
        order = self._sale()
        with self.assertRaises(StockError):
            deliver(order, None)

    def test_allow_negative_setting_is_respected(self):
        save_values(self.company, "inventory", {"allow_negative": True})
        order = self._sale(qty=15)  # أكتر من الرصيد (10)
        deliver(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("-5"))

    # ---------- المشتريات ----------
    def test_purchase_cannot_be_received_twice(self):
        order = self._purchase("PO-1", self.prod, 5, 40)
        receive_order(order, self.wh)
        with self.assertRaises(ValueError):
            receive_order(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("15"))

    def test_purchase_draft_needs_confirmation(self):
        order = self._purchase("PO-2", self.prod, 5, 40, status="draft")
        with self.assertRaises(ValueError):
            receive_order(order, self.wh)
        confirm_purchase(order)
        receive_order(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("15"))

    def test_receipt_updates_weighted_average_cost(self):
        fresh = Product.objects.create(company=self.company, code="P2", name="صنف جديد")
        receive_order(self._purchase("PO-3", fresh, 10, 40), self.wh)
        fresh.refresh_from_db()
        self.assertEqual(fresh.cost, Decimal("40.00"))
        receive_order(self._purchase("PO-4", fresh, 10, 60), self.wh)
        fresh.refresh_from_db()
        self.assertEqual(fresh.cost, Decimal("50.00"))  # (10×40 + 10×60) ÷ 20


class NumberingAndSettingsTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="شركة ترقيم", code="NUM")

    def test_prefix_setting_is_used_for_next_number(self):
        self.assertEqual(_next_number(SalesOrder, self.company, "sales"), "SO-0001")
        save_values(self.company, "sales", {"prefix": "INV"})
        self.assertEqual(_next_number(SalesOrder, self.company, "sales"), "INV-0001")
        self.assertEqual(_next_number(PurchaseOrder, self.company, "purchasing"), "PO-0001")

    def test_company_name_setting_defaults_to_company_name(self):
        self.assertEqual(current_values(self.company, "settings")["company_name"], "شركة ترقيم")


class BarcodeTests(TestCase):
    def setUp(self):
        self.a = Company.objects.create(name="شركة أ", code="BCA")
        self.b = Company.objects.create(name="شركة ب", code="BCB")
        self.prod = Product.objects.create(company=self.a, code="A1", name="صنف أ", barcode="111",
                                           sale_price=Decimal("25"), cost=Decimal("10"))

    def _product_data(self, **extra):
        data = {"code": "NEW", "name": "صنف جديد", "barcode": "", "unit": "قطعة",
                "sale_price": "1", "cost": "0", "min_qty": "0"}
        data.update(extra)
        return data

    def test_barcode_is_unique_inside_company_only(self):
        same_company = ProductForm(self._product_data(barcode="111"), instance=Product(company=self.a))
        self.assertFalse(same_company.is_valid())
        self.assertIn("barcode", same_company.errors)
        other_company = ProductForm(self._product_data(barcode="111"), instance=Product(company=self.b))
        self.assertTrue(other_company.is_valid(), other_company.errors)

    def test_blank_barcode_can_repeat(self):
        Product.objects.create(company=self.a, code="A2", name="بدون باركود 1")
        Product.objects.create(company=self.a, code="A3", name="بدون باركود 2")
        self.assertEqual(Product.objects.filter(company=self.a, barcode="").count(), 2)

    def test_editing_product_keeps_its_own_barcode(self):
        form = ProductForm(self._product_data(code="A1", name="صنف أ", barcode="111"), instance=self.prod)
        self.assertTrue(form.is_valid(), form.errors)

    def test_sales_line_resolves_product_by_barcode_and_takes_price_from_product(self):
        form = SalesLineForm({"barcode": "111", "qty": "2", "price": ""}, company=self.a)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["product"], self.prod)
        self.assertEqual(form.cleaned_data["price"], Decimal("25.00"))

    def test_purchase_line_takes_cost_from_product(self):
        form = PurchaseLineForm({"barcode": "111", "qty": "1", "cost": ""}, company=self.a)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cost"], Decimal("10.00"))

    def test_unknown_barcode_and_other_company_barcode_are_rejected(self):
        unknown = SalesLineForm({"barcode": "999", "qty": "1", "price": "5"}, company=self.a)
        self.assertFalse(unknown.is_valid())
        self.assertIn("barcode", unknown.errors)
        wrong_company = SalesLineForm({"barcode": "111", "qty": "1", "price": "5"}, company=self.b)
        self.assertFalse(wrong_company.is_valid())
        self.assertIn("barcode", wrong_company.errors)

    def test_line_needs_a_product_or_a_barcode(self):
        form = SalesLineForm({"barcode": "", "product": "", "qty": "1", "price": "5"}, company=self.a)
        self.assertFalse(form.is_valid())
        self.assertIn("product", form.errors)

    def test_line_quantity_must_be_positive(self):
        form = SalesLineForm({"barcode": "111", "qty": "0", "price": "5"}, company=self.a)
        self.assertFalse(form.is_valid())
        self.assertIn("qty", form.errors)


class ScreensAndPasswordTests(TestCase):
    def setUp(self):
        SeedModules().handle()
        self.company = Company.objects.create(name="شركة شاشات", code="SCR")
        for code in ("sales", "inventory"):
            CompanyModule.objects.update_or_create(company=self.company, module=Module.objects.get(code=code),
                                                   defaults={"enabled": True})
        User = get_user_model()
        self.user = User.objects.create_user(username="m1", password="Old-Pass-2026x", company=self.company,
                                             is_company_manager=True)
        self.customer = Partner.objects.create(company=self.company, name="عميل", kind="customer")
        self.prod = Product.objects.create(company=self.company, code="P1", name="صنف للبحث", barcode="777")

    def _order(self, status="confirmed", number="SO-1", company=None):
        if company is None:
            company, customer, product = self.company, self.customer, self.prod
        else:
            customer = Partner.objects.create(company=company, name="عميل تاني")
            product = Product.objects.create(company=company, code="X", name="س")
        order = SalesOrder.objects.create(company=company, number=number, customer=customer, status=status)
        SalesLine.objects.create(order=order, product=product, qty=1, price=10)
        return order

    def test_home_page_renders_for_manager(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_forced_password_change_redirects_until_changed(self):
        self.user.must_change_password = True
        self.user.save()
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get("/"), "/accounts/password/", fetch_redirect_response=False)
        response = self.client.post("/accounts/password/", {
            "old_password": "Old-Pass-2026x", "new_password1": "Vq7-mLx29-zTb", "new_password2": "Vq7-mLx29-zTb"})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password("Vq7-mLx29-zTb"))
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_deliver_without_warehouse_does_not_crash(self):
        order = self._order()  # مفيش مخزن للشركة، ومفيش رصيد
        self.client.force_login(self.user)
        response = self.client.post(f"/sales/orders/{order.pk}/deliver/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Warehouse.objects.filter(company=self.company).exists())  # اتعمل مخزن رئيسي تلقائي
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")  # الرصيد مش كافي فالتسليم اترجع

    def test_confirm_view_moves_draft_to_confirmed(self):
        order = self._order(status="draft")
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(f"/sales/orders/{order.pk}/confirm/").status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    def test_other_company_order_is_not_reachable(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        order = self._order(company=other, number="SO-X")
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(f"/sales/orders/{order.pk}/deliver/").status_code, 404)

    def test_product_list_search_finds_product_by_barcode(self):
        self.client.force_login(self.user)
        response = self.client.get("/inventory/products/?q=777")
        self.assertContains(response, "صنف للبحث")
