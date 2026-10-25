from decimal import Decimal

from django.test import TestCase

from accounting.services import post_purchase, post_sale, trial_balance
from core.models import Company, Module, Partner
from core.services import set_module
from inventory.models import Product, Warehouse
from inventory.services import receive
from purchasing.models import PurchaseLine, PurchaseOrder
from purchasing.services import receive_order
from sales.models import SalesLine, SalesOrder
from sales.services import deliver


class AccountingPostingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="شركة قيود", code="ACC")
        self.wh = Warehouse.objects.create(company=self.company, code="M", name="رئيسي")
        self.prod = Product.objects.create(company=self.company, code="P1", name="منتج", sale_price=Decimal("100"),
                                           cost=Decimal("60"))
        self.supplier = Partner.objects.create(company=self.company, name="مورد", kind="supplier")
        self.customer = Partner.objects.create(company=self.company, name="عميل", kind="customer")

    def test_sale_entry_is_balanced_and_matches_trial_balance(self):
        receive(company=self.company, product=self.prod, warehouse=self.wh, qty=10)
        order = SalesOrder.objects.create(company=self.company, number="SO-T1", customer=self.customer)
        SalesLine.objects.create(order=order, product=self.prod, qty=2, price=Decimal("100"))
        deliver(order, self.wh)
        rows, d, c = trial_balance(self.company)
        self.assertEqual(d, c)
        self.assertGreater(d, 0)

    def test_sale_posting_twice_creates_one_entry(self):
        order = SalesOrder.objects.create(company=self.company, number="SO-T2", customer=self.customer)
        SalesLine.objects.create(order=order, product=self.prod, qty=1, price=Decimal("50"))
        first = post_sale(order)
        second = post_sale(order)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_purchase_receipt_posts_inventory_and_payable(self):
        order = PurchaseOrder.objects.create(company=self.company, number="PO-T1", supplier=self.supplier)
        PurchaseLine.objects.create(order=order, product=self.prod, qty=5, cost=Decimal("40"))
        receive_order(order, self.wh)
        rows, d, c = trial_balance(self.company)
        self.assertEqual(d, c)
