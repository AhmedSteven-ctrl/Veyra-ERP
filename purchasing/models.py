from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum

from core.models import Company, Partner, TimeStampedModel
from inventory.models import Product

PAYMENT_LABELS = {"none": "—", "unpaid": "غير مدفوع", "partial": "مدفوع جزئياً", "paid": "مدفوع"}


def payment_state(billed, paid):
    """حالة الدفع: none (لسه ما اتفوترش) / unpaid / partial / paid."""
    if billed <= 0:
        return "none"
    if paid <= 0:
        return "unpaid"
    return "paid" if paid >= billed else "partial"


class PurchaseOrder(TimeStampedModel):
    STATUS = [("draft", "مسودة"), ("confirmed", "بانتظار الاستلام"), ("received", "مستلم"), ("cancelled", "ملغي")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_orders")
    number = models.CharField("الرقم", max_length=30)
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField("الحالة", max_length=12, choices=STATUS, default="confirmed")
    expected_date = models.DateField("تاريخ الاستلام المتوقع", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    # المستحق للمورد (الإجمالي + الضريبة) كما اتسجّل في القيد وقت الاستلام. بيتحدد تلقائي ومبيتعدلش بإيد.
    billed_total = models.DecimalField("المستحق للمورد", max_digits=14, decimal_places=2,
                                       default=Decimal("0"), editable=False)

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def total(self):
        return sum((l.subtotal for l in self.lines.all()), Decimal("0"))

    @property
    def paid(self):
        return self.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def balance(self):
        """المتبقي للمورد."""
        return self.billed_total - self.paid

    @property
    def payment_state(self):
        return payment_state(self.billed_total, self.paid)


class PurchaseLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_lines")
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    cost = models.DecimalField(max_digits=14, decimal_places=2)

    @property
    def subtotal(self):
        return self.qty * self.cost


class PurchasePayment(TimeStampedModel):
    """دفعة للمورد على أمر شراء مستلم. كل دفعة ليها قيد (مدين الموردين، دائن النقدية والبنك)."""
    METHODS = [("cash", "نقدي"), ("bank", "تحويل بنكي")]

    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField("المبلغ", max_digits=14, decimal_places=2)
    method = models.CharField("طريقة الدفع", max_length=10, choices=METHODS, default="cash")
    note = models.CharField("ملاحظة", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["created_at", "id"]
