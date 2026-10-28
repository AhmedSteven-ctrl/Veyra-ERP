"""اختبارات مديول المشتريات كامل: الموديل، الخدمات (تأكيد/استلام/إلغاء/دفع)، القيود المحاسبية،
الفورمز، والشاشات (الصلاحيات وعزل الشركات)."""
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounting.models import JournalEntry
from accounting.services import purchase_amounts, trial_balance
from core.management.commands.seed_modules import Command as SeedModules
from core.models import Company, CompanyModule, Module, Partner
from core.settings_schema import save_values
from core.views import _next_number, _save_with_number
from inventory.models import Product, StockMove, Warehouse
from inventory.services import StockError, on_hand
from purchasing.forms import PurchaseLineFormSet, PurchaseOrderForm, PurchasePaymentForm
from purchasing.models import PAYMENT_LABELS, PurchaseLine, PurchaseOrder, PurchasePayment, payment_state
from purchasing.services import cancel_order, confirm_order, pay_order, receive_order


class PurchasingBase(TestCase):
    """شركة فيها مخزن ومورد وصنفين. الأمر الافتراضي: 10 × 40 = 400 + ضريبة 14% (56) = 456."""

    def setUp(self):
        self.company = Company.objects.create(name="شركة مشتريات", code="PUR")
        self.wh = Warehouse.objects.create(company=self.company, code="M", name="رئيسي")
        self.supplier = Partner.objects.create(company=self.company, name="مورد الأمل", kind="supplier")
        self.prod = Product.objects.create(company=self.company, code="P1", name="صنف أول", barcode="555",
                                           cost=Decimal("12"))
        self.prod2 = Product.objects.create(company=self.company, code="P2", name="صنف تاني")

    def make_order(self, number="PO-1", status="confirmed", lines=None, company=None, supplier=None):
        company = company or self.company
        order = PurchaseOrder.objects.create(company=company, number=number, status=status,
                                             supplier=supplier or self.supplier)
        for product, qty, cost in (lines if lines is not None else [(self.prod, 10, 40)]):
            PurchaseLine.objects.create(order=order, product=product, qty=qty, cost=cost)
        return order

    def received_order(self, number="PO-1", lines=None):
        order = self.make_order(number, lines=lines)
        receive_order(order, self.wh)
        return order

    def entry_lines(self, journal, reference):
        entry = JournalEntry.objects.get(company=self.company, journal__code=journal, reference=reference)
        return {l.account.code: (l.debit, l.credit) for l in entry.lines.select_related("account")}


# ============================== الموديل ==============================
class PurchaseModelTests(PurchasingBase):
    def test_total_is_sum_of_lines(self):
        order = self.make_order(lines=[(self.prod, 2, 10), (self.prod2, 3, 5)])
        self.assertEqual(order.total, Decimal("35"))

    def test_new_order_defaults(self):
        order = self.make_order()
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(order.billed_total, Decimal("0"))
        self.assertEqual(str(order), "PO-1")

    def test_payment_state_function(self):
        self.assertEqual(payment_state(Decimal("0"), Decimal("0")), "none")
        self.assertEqual(payment_state(Decimal("100"), Decimal("0")), "unpaid")
        self.assertEqual(payment_state(Decimal("100"), Decimal("40")), "partial")
        self.assertEqual(payment_state(Decimal("100"), Decimal("100")), "paid")
        self.assertEqual(payment_state(Decimal("100"), Decimal("150")), "paid")
        self.assertEqual(set(PAYMENT_LABELS), {"none", "unpaid", "partial", "paid"})

    def test_paid_balance_and_state_follow_payments(self):
        order = self.received_order()
        self.assertEqual((order.paid, order.balance, order.payment_state), (Decimal("0"), Decimal("456.00"), "unpaid"))
        PurchasePayment.objects.create(order=order, amount=Decimal("100"))
        self.assertEqual((order.paid, order.balance, order.payment_state),
                         (Decimal("100"), Decimal("356.00"), "partial"))
        PurchasePayment.objects.create(order=order, amount=Decimal("356"))
        self.assertEqual((order.balance, order.payment_state), (Decimal("0.00"), "paid"))

    def test_number_is_unique_inside_company_only(self):
        self.make_order("PO-1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_order("PO-1")
        other = Company.objects.create(name="شركة تانية", code="OTH")
        other_supplier = Partner.objects.create(company=other, name="مورد", kind="supplier")
        other_prod = Product.objects.create(company=other, code="X", name="س")
        self.make_order("PO-1", company=other, supplier=other_supplier, lines=[(other_prod, 1, 1)])

    def test_order_with_payments_cannot_be_deleted(self):
        order = self.received_order()
        pay_order(order, Decimal("10"))
        with self.assertRaises(ProtectedError):
            order.delete()


# ============================== التأكيد والإلغاء ==============================
class ConfirmAndCancelTests(PurchasingBase):
    def test_draft_becomes_confirmed(self):
        order = self.make_order(status="draft")
        confirm_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    def test_confirm_twice_is_refused(self):
        order = self.make_order(status="draft")
        confirm_order(order)
        with self.assertRaisesMessage(ValueError, "مؤكد قبل كده"):
            confirm_order(order)

    def test_empty_order_cannot_be_confirmed(self):
        order = self.make_order(status="draft", lines=[])
        with self.assertRaisesMessage(ValueError, "مفيهوش أصناف"):
            confirm_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, "draft")

    def test_cancelled_and_received_orders_cannot_be_confirmed(self):
        cancelled = self.make_order("PO-C", status="cancelled")
        with self.assertRaisesMessage(ValueError, "ملغي"):
            confirm_order(cancelled)
        received = self.received_order("PO-R")
        with self.assertRaisesMessage(ValueError, "اتستلم"):
            confirm_order(received)

    def test_cancel_draft_and_confirmed(self):
        for number, status in (("PO-D", "draft"), ("PO-K", "confirmed")):
            order = self.make_order(number, status=status)
            cancel_order(order)
            order.refresh_from_db()
            self.assertEqual(order.status, "cancelled")

    def test_cancel_creates_no_stock_and_no_journal(self):
        order = self.make_order()
        cancel_order(order)
        self.assertEqual(StockMove.objects.filter(company=self.company).count(), 0)
        self.assertEqual(JournalEntry.objects.filter(company=self.company).count(), 0)

    def test_received_order_cannot_be_cancelled(self):
        order = self.received_order()
        with self.assertRaisesMessage(ValueError, "اتستلم"):
            cancel_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, "received")
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))

    def test_cancel_twice_is_refused(self):
        order = self.make_order()
        cancel_order(order)
        with self.assertRaisesMessage(ValueError, "ملغي قبل كده"):
            cancel_order(order)

    def test_cancelled_order_cannot_be_received(self):
        order = self.make_order()
        cancel_order(order)
        with self.assertRaisesMessage(ValueError, "ملغي"):
            receive_order(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("0"))

    def test_stale_copy_cannot_receive_after_cancel(self):
        order = self.make_order()
        stale = PurchaseOrder.objects.get(pk=order.pk)
        cancel_order(order)
        with self.assertRaises(ValueError):
            receive_order(stale, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("0"))


# ============================== الاستلام ==============================
class ReceiveOrderTests(PurchasingBase):
    def test_receive_adds_stock_sets_status_and_billed_total(self):
        order = self.make_order()
        receive_order(order, self.wh)
        self.assertEqual(order.status, "received")
        self.assertEqual(order.billed_total, Decimal("456.00"))
        stored = PurchaseOrder.objects.get(pk=order.pk)
        self.assertEqual((stored.status, stored.billed_total), ("received", Decimal("456.00")))
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))
        move = StockMove.objects.get(company=self.company, reference="PO-1")
        self.assertEqual((move.kind, move.qty, move.warehouse), ("receipt", Decimal("10"), self.wh))

    def test_receive_posts_balanced_purchase_entry(self):
        self.received_order()
        self.assertEqual(self.entry_lines("PUR", "PO-1"), {
            "1300": (Decimal("400"), Decimal("0")),
            "1400": (Decimal("56"), Decimal("0")),
            "2100": (Decimal("0"), Decimal("456")),
        })

    def test_billed_total_equals_payable_credit(self):
        order = self.received_order()
        self.assertEqual(self.entry_lines("PUR", "PO-1")["2100"][1], order.billed_total)

    def test_multi_line_totals_and_vat(self):
        order = self.received_order(lines=[(self.prod, 10, 40), (self.prod2, 5, 20)])
        self.assertEqual(order.billed_total, Decimal("570.00"))  # 500 + 14%
        self.assertEqual(self.entry_lines("PUR", "PO-1")["1400"][0], Decimal("70"))
        self.assertEqual(on_hand(self.company, self.prod2, self.wh), Decimal("5"))

    def test_purchase_tax_setting_applies_to_new_receipts_only(self):
        first = self.received_order("PO-1")
        save_values(self.company, "accounting", {"default_purchase_tax": Decimal("0")})
        second = self.received_order("PO-2")
        first.refresh_from_db()
        self.assertEqual(first.billed_total, Decimal("456.00"))
        self.assertEqual(second.billed_total, Decimal("400.00"))
        self.assertNotIn("1400", self.entry_lines("PUR", "PO-2"))  # الضريبة صفر فمفيش سطر ليها

    def test_purchase_amounts_helper(self):
        order = self.make_order()
        self.assertEqual(purchase_amounts(order), (Decimal("400.00"), Decimal("56.00"), Decimal("456.00")))

    def test_zero_cost_order_has_no_entry_and_nothing_to_pay(self):
        order = self.received_order(lines=[(self.prod, 3, 0)])
        self.assertEqual(order.billed_total, Decimal("0"))
        self.assertEqual(JournalEntry.objects.filter(company=self.company, journal__code="PUR").count(), 0)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("3"))
        with self.assertRaisesMessage(ValueError, "مفيهوش مستحقات"):
            pay_order(order, Decimal("1"))

    def test_weighted_average_cost_across_lines_of_same_product(self):
        self.received_order(lines=[(self.prod, 10, 40), (self.prod, 10, 60)])
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.cost, Decimal("50.00"))
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("20"))

    def test_receive_twice_is_refused(self):
        order = self.received_order()
        with self.assertRaisesMessage(ValueError, "اتستلم قبل كده"):
            receive_order(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))
        self.assertEqual(JournalEntry.objects.filter(company=self.company, journal__code="PUR").count(), 1)

    def test_double_click_with_stale_copy_receives_once(self):
        order = self.make_order()
        first, second = PurchaseOrder.objects.get(pk=order.pk), PurchaseOrder.objects.get(pk=order.pk)
        receive_order(first, self.wh)
        with self.assertRaises(ValueError):
            receive_order(second, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))

    def test_draft_must_be_confirmed_first(self):
        order = self.make_order(status="draft")
        with self.assertRaisesMessage(ValueError, "لازم تأكّد الأمر الأول"):
            receive_order(order, self.wh)
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("0"))

    def test_empty_order_is_refused_and_status_rolls_back(self):
        order = self.make_order(lines=[])
        with self.assertRaisesMessage(ValueError, "مفيهوش أصناف"):
            receive_order(order, self.wh)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    def test_receive_needs_a_warehouse(self):
        order = self.make_order()
        with self.assertRaises(StockError):
            receive_order(order, None)

    def test_other_company_warehouse_is_refused_and_everything_rolls_back(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        foreign_wh = Warehouse.objects.create(company=other, code="F", name="مخزن غريب")
        order = self.make_order()
        with self.assertRaises(StockError):
            receive_order(order, foreign_wh)
        order.refresh_from_db()
        self.prod.refresh_from_db()
        self.assertEqual((order.status, self.prod.cost), ("confirmed", Decimal("12.00")))
        self.assertEqual(StockMove.objects.count(), 0)

    def test_failure_while_posting_rolls_back_stock_cost_status_and_billed_total(self):
        order = self.make_order()
        with mock.patch("accounting.services.post_purchase", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                receive_order(order, self.wh)
        order.refresh_from_db()
        self.prod.refresh_from_db()
        self.assertEqual((order.status, order.billed_total), ("confirmed", Decimal("0")))
        self.assertEqual(self.prod.cost, Decimal("12.00"))
        self.assertEqual(StockMove.objects.count(), 0)


# ============================== الدفع للمورد ==============================
class SupplierPaymentTests(PurchasingBase):
    def setUp(self):
        super().setUp()
        self.order = self.received_order()  # المستحق 456

    def test_full_payment_closes_the_balance(self):
        payment = pay_order(self.order, Decimal("456"))
        self.assertEqual(payment.amount, Decimal("456.00"))
        self.assertEqual((self.order.paid, self.order.balance, self.order.payment_state),
                         (Decimal("456.00"), Decimal("0.00"), "paid"))

    def test_partial_payments_add_up(self):
        pay_order(self.order, Decimal("200"))
        self.assertEqual((self.order.balance, self.order.payment_state), (Decimal("256.00"), "partial"))
        pay_order(self.order, Decimal("256"))
        self.assertEqual((self.order.balance, self.order.payment_state), (Decimal("0.00"), "paid"))
        self.assertEqual(self.order.payments.count(), 2)

    def test_overpayment_is_refused(self):
        with self.assertRaisesMessage(ValueError, "أكبر من المتبقي"):
            pay_order(self.order, Decimal("500"))
        self.assertEqual(self.order.payments.count(), 0)

    def test_second_payment_cannot_exceed_what_is_left(self):
        pay_order(self.order, Decimal("400"))
        with self.assertRaisesMessage(ValueError, "أكبر من المتبقي"):
            pay_order(self.order, Decimal("100"))
        self.assertEqual(self.order.paid, Decimal("400.00"))

    def test_paid_order_accepts_no_more_payments(self):
        pay_order(self.order, Decimal("456"))
        with self.assertRaises(ValueError):
            pay_order(self.order, Decimal("1"))

    def test_zero_and_negative_amounts_are_refused(self):
        for amount in (Decimal("0"), Decimal("-5")):
            with self.assertRaisesMessage(ValueError, "أكبر من صفر"):
                pay_order(self.order, amount)
        self.assertEqual(self.order.payments.count(), 0)

    def test_only_received_orders_can_be_paid(self):
        for number, status in (("PO-D", "draft"), ("PO-K", "confirmed"), ("PO-X", "cancelled")):
            order = self.make_order(number, status=status)
            with self.assertRaisesMessage(ValueError, "بعد استلام الأمر"):
                pay_order(order, Decimal("10"))

    def test_unknown_method_is_refused(self):
        with self.assertRaisesMessage(ValueError, "طريقة الدفع"):
            pay_order(self.order, Decimal("10"), method="crypto")

    def test_amount_is_rounded_to_two_decimals(self):
        payment = pay_order(self.order, Decimal("100.005"))
        self.assertEqual(payment.amount, Decimal("100.01"))

    def test_method_note_and_user_are_saved(self):
        user = get_user_model().objects.create_user(username="payer", password="x", company=self.company)
        payment = pay_order(self.order, Decimal("50"), method="bank", note="x" * 300, user=user)
        payment.refresh_from_db()
        self.assertEqual((payment.method, len(payment.note), payment.created_by), ("bank", 200, user))

    def test_each_payment_posts_its_own_balanced_entry(self):
        first = pay_order(self.order, Decimal("200"))
        second = pay_order(self.order, Decimal("100"))
        self.assertEqual(self.entry_lines("PAY", f"PO-1-P{first.pk}"),
                         {"2100": (Decimal("200"), Decimal("0")), "1010": (Decimal("0"), Decimal("200"))})
        self.assertEqual(self.entry_lines("PAY", f"PO-1-P{second.pk}"),
                         {"2100": (Decimal("100"), Decimal("0")), "1010": (Decimal("0"), Decimal("100"))})
        self.assertEqual(JournalEntry.objects.filter(company=self.company, journal__code="PAY").count(), 2)

    def test_trial_balance_stays_balanced_and_payable_clears_after_full_payment(self):
        pay_order(self.order, Decimal("456"))
        rows, total_d, total_c = trial_balance(self.company)
        self.assertEqual(total_d, total_c)
        payable = next(r for r in rows if r["account"].code == "2100")
        cash = next(r for r in rows if r["account"].code == "1010")
        self.assertEqual((payable["debit"], payable["credit"]), (Decimal("456"), Decimal("456")))
        self.assertEqual(cash["credit"], Decimal("456"))

    def test_failure_while_posting_leaves_no_payment(self):
        with mock.patch("accounting.services.post_supplier_payment", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                pay_order(self.order, Decimal("100"))
        self.assertEqual(PurchasePayment.objects.count(), 0)
        self.assertEqual(JournalEntry.objects.filter(company=self.company, journal__code="PAY").count(), 0)


# ============================== الفورمز ==============================
class PurchaseFormTests(PurchasingBase):
    def order_form(self, **data):
        return PurchaseOrderForm(data, company=self.company, instance=PurchaseOrder(company=self.company))

    def test_supplier_choices_are_suppliers_of_this_company_only(self):
        customer = Partner.objects.create(company=self.company, name="عميل", kind="customer")
        both = Partner.objects.create(company=self.company, name="الاتنين", kind="both")
        other = Company.objects.create(name="شركة تانية", code="OTH")
        foreign = Partner.objects.create(company=other, name="مورد غريب", kind="supplier")
        self.assertTrue(self.order_form(supplier=self.supplier.pk).is_valid())
        self.assertTrue(self.order_form(supplier=both.pk).is_valid())
        self.assertFalse(self.order_form(supplier=customer.pk).is_valid())
        self.assertFalse(self.order_form(supplier=foreign.pk).is_valid())

    def test_expected_date_and_notes_are_optional_and_saved(self):
        self.assertTrue(self.order_form(supplier=self.supplier.pk).is_valid())
        form = self.order_form(supplier=self.supplier.pk, expected_date="2026-11-01", notes="تسليم الصبح")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["expected_date"], date(2026, 11, 1))
        self.assertFalse(self.order_form(supplier=self.supplier.pk, expected_date="بكرة").is_valid())

    def test_payment_form_defaults_to_the_remaining_balance(self):
        order = self.received_order()
        form = PurchasePaymentForm(order=order)
        self.assertEqual(form.fields["amount"].initial, Decimal("456.00"))
        self.assertIn("456", form.fields["amount"].label)

    def test_payment_form_validation(self):
        order = self.received_order()
        self.assertTrue(PurchasePaymentForm({"amount": "456", "method": "cash"}, order=order).is_valid())
        self.assertTrue(PurchasePaymentForm({"amount": "10.5", "method": "bank", "note": "دفعة"}, order=order).is_valid())
        for bad in ({"amount": "457", "method": "cash"}, {"amount": "0", "method": "cash"},
                    {"amount": "-1", "method": "cash"}, {"amount": "10", "method": "crypto"}, {"method": "cash"}):
            self.assertFalse(PurchasePaymentForm(bad, order=order).is_valid(), bad)

    def formset(self, rows):
        data = {"lines-TOTAL_FORMS": str(len(rows)), "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000"}
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f"lines-{i}-{key}"] = str(value)
        return PurchaseLineFormSet(data, instance=PurchaseOrder(company=self.company),
                                   form_kwargs={"company": self.company})

    def test_order_needs_at_least_one_line(self):
        self.assertFalse(self.formset([{"barcode": "", "product": "", "qty": "", "cost": ""}]).is_valid())

    def test_line_by_barcode_takes_cost_from_product(self):
        formset = self.formset([{"barcode": "555", "product": "", "qty": 3, "cost": ""}])
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertEqual(formset.forms[0].cleaned_data["product"], self.prod)
        self.assertEqual(formset.forms[0].cleaned_data["cost"], Decimal("12.00"))

    def test_line_by_product_with_explicit_cost(self):
        formset = self.formset([{"product": self.prod2.pk, "qty": 2, "cost": 7.5}])
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_bad_lines_are_rejected(self):
        for row in ({"product": self.prod.pk, "qty": 0, "cost": 5}, {"product": self.prod.pk, "qty": 1, "cost": -1},
                    {"barcode": "000", "qty": 1, "cost": 5}, {"qty": 1, "cost": 5}):
            self.assertFalse(self.formset([row]).is_valid(), row)

    def test_other_company_product_is_rejected(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        foreign = Product.objects.create(company=other, code="F1", name="غريب", barcode="999")
        self.assertFalse(self.formset([{"product": foreign.pk, "qty": 1, "cost": 5}]).is_valid())
        self.assertFalse(self.formset([{"barcode": "999", "qty": 1, "cost": 5}]).is_valid())


# ============================== الشاشات ==============================
class PurchaseViewTests(PurchasingBase):
    def setUp(self):
        super().setUp()
        SeedModules().handle()
        for code in ("purchasing", "accounting", "inventory"):
            CompanyModule.objects.update_or_create(company=self.company, module=Module.objects.get(code=code),
                                                   defaults={"enabled": True})
        User = get_user_model()
        self.boss = User.objects.create_user(username="boss", password="x", company=self.company,
                                             is_company_manager=True)
        self.clerk = User.objects.create_user(username="clerk", password="x", company=self.company)
        self.clerk.allowed_modules.set([Module.objects.get(code="purchasing")])
        self.nobody = User.objects.create_user(username="nobody", password="x", company=self.company)
        self.client.force_login(self.boss)

    # ----- أدوات -----
    def msgs(self, response):
        """رسائل الطلب. ملاحظة: الرسائل اللي لسه ما اتعرضتش من طلبات سابقة بتظهر هنا كمان، فبنفحص بـ assertIn."""
        return [str(m) for m in get_messages(response.wsgi_request)]

    def lines_data(self, rows, initial=0):
        data = {"lines-TOTAL_FORMS": str(len(rows)), "lines-INITIAL_FORMS": str(initial),
                "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000"}
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f"lines-{i}-{key}"] = str(value)
        return data

    def new_order_data(self, rows=None, **header):
        data = {"supplier": self.supplier.pk, "expected_date": "", "notes": ""}
        data.update(header)
        data.update(self.lines_data(rows or [{"product": self.prod.pk, "qty": 4, "cost": 10}]))
        return data

    def other_company_order(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        supplier = Partner.objects.create(company=other, name="مورد غريب", kind="supplier")
        product = Product.objects.create(company=other, code="X", name="غريب")
        return self.make_order("PO-X", company=other, supplier=supplier, lines=[(product, 1, 1)])

    # ----- الصلاحيات -----
    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get("/purchasing/orders/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_user_without_purchasing_access_gets_403_everywhere(self):
        order = self.make_order()
        self.client.force_login(self.nobody)
        for path in ("/purchasing/orders/", f"/purchasing/orders/{order.pk}/", "/purchasing/orders/new/",
                     f"/purchasing/orders/{order.pk}/edit/", f"/purchasing/orders/{order.pk}/pay/",
                     "/purchasing/payments/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        for action in ("confirm", "receive", "cancel"):
            self.assertEqual(self.client.post(f"/purchasing/orders/{order.pk}/{action}/").status_code, 403, action)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    def test_clerk_without_accounting_access_cannot_pay(self):
        order = self.received_order()
        self.client.force_login(self.clerk)
        self.assertEqual(self.client.get(f"/purchasing/orders/{order.pk}/pay/").status_code, 403)
        self.assertEqual(self.client.post(f"/purchasing/orders/{order.pk}/pay/", {"amount": "10", "method": "cash"}).status_code, 403)
        self.assertEqual(order.payments.count(), 0)
        detail = self.client.get(f"/purchasing/orders/{order.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("purchase_pay", [a["url"] for a in detail.context["actions"]])

    def test_post_only_endpoints_reject_get(self):
        order = self.make_order()
        for action in ("confirm", "receive", "cancel"):
            self.assertEqual(self.client.get(f"/purchasing/orders/{order.pk}/{action}/").status_code, 405, action)

    def test_other_company_order_is_not_reachable_from_any_screen(self):
        foreign = self.other_company_order()
        for path in (f"/purchasing/orders/{foreign.pk}/", f"/purchasing/orders/{foreign.pk}/edit/",
                     f"/purchasing/orders/{foreign.pk}/pay/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        for action in ("confirm", "receive", "cancel", "pay"):
            self.assertEqual(self.client.post(f"/purchasing/orders/{foreign.pk}/{action}/").status_code, 404, action)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "confirmed")

    # ----- القايمة -----
    def test_list_shows_orders_payment_state_and_hides_other_companies(self):
        self.make_order("PO-1", status="draft")
        received = self.received_order("PO-2")
        pay_order(received, Decimal("100"))
        self.make_order("PO-3", status="cancelled")
        self.other_company_order()
        response = self.client.get("/purchasing/orders/")
        self.assertEqual(response.status_code, 200)
        rows = {r["cells"][0]: r for r in response.context["rows"]}
        self.assertEqual(set(rows), {"PO-1", "PO-2", "PO-3"})
        self.assertEqual(rows["PO-2"]["cells"][3], PAYMENT_LABELS["partial"])
        self.assertEqual(rows["PO-1"]["cells"][3], "—")
        self.assertEqual(rows["PO-1"]["action"][0], "purchase_confirm")
        self.assertIsNone(rows["PO-2"]["action"])
        stats = {s["key"]: s["count"] for s in response.context["stats"]}
        self.assertEqual((stats[""], stats["draft"], stats["received"], stats["cancelled"]), (3, 1, 1, 1))

    def test_list_filter_and_search(self):
        self.make_order("PO-1", status="draft")
        self.received_order("PO-2")
        filtered = self.client.get("/purchasing/orders/?f=received")
        self.assertEqual([r["cells"][0] for r in filtered.context["rows"]], ["PO-2"])
        searched = self.client.get("/purchasing/orders/?q=PO-1")
        self.assertEqual([r["cells"][0] for r in searched.context["rows"]], ["PO-1"])
        by_supplier = self.client.get("/purchasing/orders/?q=الأمل")
        self.assertEqual(len(by_supplier.context["rows"]), 2)

    # ----- الإنشاء -----
    def test_create_order_with_header_fields_and_numbering(self):
        response = self.client.post("/purchasing/orders/new/",
                                    self.new_order_data(expected_date="2026-12-01", notes="تسليم الصبح"))
        self.assertEqual(response.status_code, 302)
        order = PurchaseOrder.objects.get(company=self.company, number="PO-0001")
        self.assertEqual((order.status, order.expected_date, order.notes, order.supplier),
                         ("confirmed", date(2026, 12, 1), "تسليم الصبح", self.supplier))
        self.assertEqual((order.lines.count(), order.total), (1, Decimal("40")))
        self.client.post("/purchasing/orders/new/", self.new_order_data())
        self.assertTrue(PurchaseOrder.objects.filter(company=self.company, number="PO-0002").exists())

    def test_create_uses_the_prefix_setting(self):
        save_values(self.company, "purchasing", {"prefix": "BUY"})
        self.client.post("/purchasing/orders/new/", self.new_order_data())
        self.assertTrue(PurchaseOrder.objects.filter(company=self.company, number="BUY-0001").exists())

    def test_create_line_by_barcode_defaults_cost_from_product(self):
        self.client.post("/purchasing/orders/new/", self.new_order_data(
            rows=[{"barcode": "555", "product": "", "qty": 4, "cost": ""}]))
        line = PurchaseLine.objects.get(order__number="PO-0001")
        self.assertEqual((line.product, line.cost), (self.prod, Decimal("12.00")))

    def test_create_without_lines_is_rejected(self):
        response = self.client.post("/purchasing/orders/new/",
                                    self.new_order_data(rows=[{"product": "", "qty": "", "cost": ""}]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.filter(company=self.company).count(), 0)

    def test_create_with_a_customer_or_foreign_supplier_is_rejected(self):
        customer = Partner.objects.create(company=self.company, name="عميل", kind="customer")
        foreign = self.other_company_order().supplier
        for supplier in (customer, foreign):
            response = self.client.post("/purchasing/orders/new/", self.new_order_data(supplier=supplier.pk))
            self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.filter(company=self.company).count(), 0)

    def test_create_form_renders(self):
        response = self.client.get("/purchasing/orders/new/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("expected_date", response.context["form"].fields)

    def test_save_with_number_retries_when_the_number_is_taken(self):
        self.make_order("PO-0001")
        order = PurchaseOrder(company=self.company, supplier=self.supplier)
        with mock.patch("core.views._next_number", side_effect=["PO-0001", "PO-0002"]):
            _save_with_number(order, "purchasing")
        self.assertEqual(order.number, "PO-0002")
        self.assertIsNotNone(order.pk)

    def test_save_with_number_gives_up_after_five_clashes(self):
        self.make_order("PO-0001")
        order = PurchaseOrder(company=self.company, supplier=self.supplier)
        with mock.patch("core.views._next_number", side_effect=["PO-0001"] * 5):
            with self.assertRaises(IntegrityError):
                _save_with_number(order, "purchasing")

    def test_next_number_skips_taken_numbers(self):
        self.make_order("PO-0002")
        self.assertEqual(_next_number(PurchaseOrder, self.company, "purchasing"), "PO-0003")

    # ----- التعديل -----
    def edit_rows(self, order):
        return [{"id": l.pk, "order": order.pk, "product": l.product_id, "qty": l.qty, "cost": l.cost, "barcode": ""}
                for l in order.lines.all()]

    def test_edit_updates_header_and_line(self):
        order = self.make_order()
        rows = self.edit_rows(order)
        rows[0]["qty"] = 7
        data = {"supplier": self.supplier.pk, "expected_date": "2026-12-15", "notes": "اتغيّرت", **self.lines_data(rows, initial=1)}
        response = self.client.post(f"/purchasing/orders/{order.pk}/edit/", data)
        self.assertEqual(response.status_code, 302)
        order = PurchaseOrder.objects.get(pk=order.pk)
        self.assertEqual((order.notes, order.expected_date, order.total), ("اتغيّرت", date(2026, 12, 15), Decimal("280")))

    def test_edit_can_add_and_delete_lines(self):
        order = self.make_order(lines=[(self.prod, 10, 40), (self.prod2, 1, 5)])
        rows = self.edit_rows(order)
        rows[1]["DELETE"] = "on"
        rows.append({"product": self.prod2.pk, "qty": 3, "cost": 6})
        data = {"supplier": self.supplier.pk, "expected_date": "", "notes": "", **self.lines_data(rows, initial=2)}
        self.assertEqual(self.client.post(f"/purchasing/orders/{order.pk}/edit/", data).status_code, 302)
        self.assertEqual(sorted(order.lines.values_list("qty", flat=True)), [Decimal("3.000"), Decimal("10.000")])

    def test_edit_cannot_remove_every_line(self):
        order = self.make_order()
        rows = self.edit_rows(order)
        rows[0]["DELETE"] = "on"
        data = {"supplier": self.supplier.pk, "expected_date": "", "notes": "", **self.lines_data(rows, initial=1)}
        self.assertEqual(self.client.post(f"/purchasing/orders/{order.pk}/edit/", data).status_code, 200)
        self.assertEqual(order.lines.count(), 1)

    def test_received_and_cancelled_orders_cannot_be_edited(self):
        received = self.received_order("PO-R")
        cancelled = self.make_order("PO-C", status="cancelled")
        for order in (received, cancelled):
            response = self.client.get(f"/purchasing/orders/{order.pk}/edit/")
            self.assertRedirects(response, f"/purchasing/orders/{order.pk}/", fetch_redirect_response=False)
        self.assertIn("الأمر اتستلم، مينفعش يتعدل", self.msgs(response))  # آخر استجابة: الأمر الملغي
        self.assertIn("الأمر ملغي، مينفعش يتعدل", self.msgs(response))

    # ----- التفاصيل -----
    def test_detail_of_confirmed_order(self):
        order = self.make_order(lines=[(self.prod, 10, 40)])
        response = self.client.get(f"/purchasing/orders/{order.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["lines"][0][1:], (Decimal("10.000"), Decimal("40.00"), Decimal("400")))
        self.assertEqual([a["url"] for a in response.context["actions"]], ["purchase_receive", "purchase_cancel"])
        self.assertEqual(response.context["edit_url"], "purchase_edit")
        self.assertEqual(response.context["tables"], [])

    def test_detail_actions_follow_the_status(self):
        draft = self.make_order("PO-D", status="draft")
        response = self.client.get(f"/purchasing/orders/{draft.pk}/")
        self.assertEqual([a["url"] for a in response.context["actions"]], ["purchase_confirm", "purchase_cancel"])

    def test_detail_of_received_order_shows_money_and_payments(self):
        order = self.received_order()
        pay_order(order, Decimal("100"), method="bank", note="الدفعة الأولى")
        response = self.client.get(f"/purchasing/orders/{order.pk}/")
        fields = dict(response.context["fields"])
        self.assertEqual((fields["المستحق للمورد"], fields["المدفوع"], fields["المتبقي"]),
                         (Decimal("456.00"), Decimal("100.00"), Decimal("356.00")))
        self.assertEqual(fields["حالة الدفع"], PAYMENT_LABELS["partial"])
        rows = response.context["tables"][0]["rows"]
        self.assertEqual((len(rows), rows[0][1], rows[0][2], rows[0][3]), (1, Decimal("100.00"), "تحويل بنكي", "الدفعة الأولى"))
        self.assertEqual([a["url"] for a in response.context["actions"]], ["purchase_pay"])
        self.assertIsNone(response.context["edit_url"])

    def test_fully_paid_order_has_no_pay_button(self):
        order = self.received_order()
        pay_order(order, Decimal("456"))
        response = self.client.get(f"/purchasing/orders/{order.pk}/")
        self.assertEqual(response.context["actions"], [])

    def test_detail_of_cancelled_order(self):
        order = self.make_order(status="cancelled")
        response = self.client.get(f"/purchasing/orders/{order.pk}/")
        self.assertIn(("الحالة", "ملغي"), response.context["fields"])
        self.assertEqual((response.context["steps"], response.context["actions"], response.context["edit_url"]), ([], [], None))

    def test_detail_shows_expected_date_and_notes(self):
        order = self.make_order()
        PurchaseOrder.objects.filter(pk=order.pk).update(expected_date=date(2026, 12, 1), notes="هاتهم بدري")
        fields = dict(self.client.get(f"/purchasing/orders/{order.pk}/").context["fields"])
        self.assertEqual((fields["تاريخ الاستلام المتوقع"], fields["ملاحظات"]), (date(2026, 12, 1), "هاتهم بدري"))

    # ----- التأكيد والاستلام والإلغاء -----
    def test_confirm_receive_cancel_views(self):
        draft = self.make_order("PO-D", status="draft")
        self.assertRedirects(self.client.post(f"/purchasing/orders/{draft.pk}/confirm/"), "/purchasing/orders/",
                             fetch_redirect_response=False)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "confirmed")

        response = self.client.post(f"/purchasing/orders/{draft.pk}/receive/")
        self.assertRedirects(response, "/purchasing/orders/", fetch_redirect_response=False)
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.billed_total), ("received", Decimal("456.00")))
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))

        other = self.make_order("PO-K")
        response = self.client.post(f"/purchasing/orders/{other.pk}/cancel/")
        self.assertRedirects(response, f"/purchasing/orders/{other.pk}/", fetch_redirect_response=False)
        other.refresh_from_db()
        self.assertEqual(other.status, "cancelled")

    def test_receiving_twice_through_the_screen_adds_stock_once(self):
        order = self.make_order()
        self.client.post(f"/purchasing/orders/{order.pk}/receive/")
        again = self.client.post(f"/purchasing/orders/{order.pk}/receive/")
        self.assertIn("الأمر اتستلم قبل كده", self.msgs(again))
        self.assertEqual(on_hand(self.company, self.prod, self.wh), Decimal("10"))

    def test_cancelling_a_received_order_shows_an_error(self):
        order = self.received_order()
        response = self.client.post(f"/purchasing/orders/{order.pk}/cancel/")
        self.assertIn("الأمر اتستلم، مينفعش يتلغي", self.msgs(response))
        order.refresh_from_db()
        self.assertEqual(order.status, "received")

    def test_receive_creates_a_default_warehouse_when_the_company_has_none(self):
        order = self.make_order()
        self.wh.delete()
        self.client.post(f"/purchasing/orders/{order.pk}/receive/")
        main = Warehouse.objects.get(company=self.company)
        self.assertEqual((main.code, on_hand(self.company, self.prod, main)), ("MAIN", Decimal("10")))

    # ----- الدفع -----
    def test_pay_screen_renders_with_the_balance_as_default(self):
        order = self.received_order()
        response = self.client.get(f"/purchasing/orders/{order.pk}/pay/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].fields["amount"].initial, Decimal("456.00"))

    def test_pay_screen_records_a_payment(self):
        order = self.received_order()
        response = self.client.post(f"/purchasing/orders/{order.pk}/pay/",
                                    {"amount": "200", "method": "bank", "note": "دفعة"})
        self.assertRedirects(response, f"/purchasing/orders/{order.pk}/", fetch_redirect_response=False)
        payment = order.payments.get()
        self.assertEqual((payment.amount, payment.method, payment.created_by), (Decimal("200.00"), "bank", self.boss))
        self.assertTrue(self.msgs(response))
        self.assertTrue(JournalEntry.objects.filter(company=self.company, journal__code="PAY").exists())

    def test_pay_screen_rejects_overpayment(self):
        order = self.received_order()
        response = self.client.post(f"/purchasing/orders/{order.pk}/pay/", {"amount": "9999", "method": "cash"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("amount", response.context["form"].errors)
        self.assertEqual(order.payments.count(), 0)

    def test_pay_screen_refuses_unreceived_and_fully_paid_orders(self):
        confirmed = self.make_order("PO-K")
        response = self.client.get(f"/purchasing/orders/{confirmed.pk}/pay/")
        self.assertRedirects(response, f"/purchasing/orders/{confirmed.pk}/", fetch_redirect_response=False)
        paid = self.received_order("PO-P")
        pay_order(paid, Decimal("456"))
        response = self.client.post(f"/purchasing/orders/{paid.pk}/pay/", {"amount": "1", "method": "cash"})
        self.assertRedirects(response, f"/purchasing/orders/{paid.pk}/", fetch_redirect_response=False)
        self.assertEqual(paid.payments.count(), 1)

    # ----- قايمة المدفوعات -----
    def test_payments_list(self):
        first, second = self.received_order("PO-1"), self.received_order("PO-2")
        pay_order(first, Decimal("100"), method="cash")
        pay_order(second, Decimal("50"), method="bank")
        foreign = self.other_company_order()
        PurchasePayment.objects.create(order=foreign, amount=Decimal("1"))
        response = self.client.get("/purchasing/payments/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(r["cells"][0] for r in response.context["rows"]), ["PO-1", "PO-2"])
        self.assertIsNone(response.context["create_url"])
        by_method = self.client.get("/purchasing/payments/?f=bank")
        self.assertEqual([r["cells"][0] for r in by_method.context["rows"]], ["PO-2"])

    # ----- الصفحات التانية ما اتأثرتش -----
    def test_trial_balance_screen_still_balances_after_purchases_and_payments(self):
        order = self.received_order()
        pay_order(order, Decimal("300"))
        rows, total_d, total_c = trial_balance(self.company)
        self.assertEqual(total_d, total_c)
        self.assertEqual(self.client.get("/accounting/trial-balance/").status_code, 200)
