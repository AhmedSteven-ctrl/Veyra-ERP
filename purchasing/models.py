from datetime import date
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


class SupplierPrice(TimeStampedModel):
    """سعر مورد لصنف (من أقل كمية معينة، ولفترة اختيارية). بيتحط تلقائي لو سيبت تكلفة سطر الأمر فاضية."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="supplier_prices")
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="supplier_prices")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="supplier_prices")
    min_qty = models.DecimalField("أقل كمية", max_digits=14, decimal_places=3, default=Decimal("1"))
    price = models.DecimalField("السعر", max_digits=14, decimal_places=2)
    valid_from = models.DateField("ساري من", null=True, blank=True)
    valid_to = models.DateField("ساري لحد", null=True, blank=True)

    class Meta:
        ordering = ["supplier__name", "product__name", "min_qty"]

    def __str__(self):
        return f"{self.supplier.name} - {self.product.name}: {self.price}"

    def status_on(self, day=None):
        """ساري / منتهي / لسه ما بدأ."""
        day = day or date.today()
        if self.valid_from and self.valid_from > day:
            return "upcoming"
        if self.valid_to and self.valid_to < day:
            return "expired"
        return "active"


class PurchaseAgreement(TimeStampedModel):
    """اتفاقية شراء مع مورد: أصناف بكميات وأسعار متفق عليها لفترة. بتتحوّل لطلبات شراء على دفعات."""
    STATUS = [("draft", "مسودة"), ("active", "ساري"), ("closed", "مغلق"), ("cancelled", "ملغي")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_agreements")
    number = models.CharField("الرقم", max_length=30)
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="agreements")
    status = models.CharField("الحالة", max_length=12, choices=STATUS, default="draft")
    start_date = models.DateField("تاريخ البداية", default=date.today)
    end_date = models.DateField("تاريخ النهاية", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def total(self):
        return sum((l.subtotal for l in self.lines.all()), Decimal("0"))


class PurchaseAgreementLine(models.Model):
    agreement = models.ForeignKey(PurchaseAgreement, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="agreement_lines")
    qty = models.DecimalField("الكمية المتفق عليها", max_digits=14, decimal_places=3)
    price = models.DecimalField("السعر المتفق عليه", max_digits=14, decimal_places=2)

    class Meta:
        unique_together = [("agreement", "product")]

    @property
    def subtotal(self):
        return self.qty * self.price

    @property
    def ordered(self):
        """الكمية اللي اتطلبت فعلاً بطلبات الشراء المرتبطة بالاتفاقية (من غير الملغي)."""
        total = (PurchaseLine.objects.filter(order__agreement_id=self.agreement_id, product_id=self.product_id)
                 .exclude(order__status="cancelled").aggregate(t=Sum("qty"))["t"])
        return total or Decimal("0")

    @property
    def remaining(self):
        return max(self.qty - self.ordered, Decimal("0"))


class PurchaseOrder(TimeStampedModel):
    STATUS = [("draft", "مسودة"), ("confirmed", "بانتظار الاستلام"), ("received", "مستلم"), ("cancelled", "ملغي")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_orders")
    number = models.CharField("الرقم", max_length=30)
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField("الحالة", max_length=12, choices=STATUS, default="confirmed")
    agreement = models.ForeignKey(PurchaseAgreement, null=True, blank=True, editable=False,
                                  on_delete=models.PROTECT, related_name="orders")
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
