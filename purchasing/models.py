from decimal import Decimal
from django.db import models
from core.models import Company, Partner, TimeStampedModel
from inventory.models import Product, Warehouse


class PurchaseAgreement(TimeStampedModel):
    AGREEMENT_TYPES = [("blanket", "أمر شراء مفتوح"), ("call", "عقد توريد")]
    STATUS = [("draft", "مسودة"), ("ongoing", "قيد التنفيذ"), ("closed", "مغلق")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_agreements")
    number = models.CharField("رقم الاتفاقية", max_length=30)
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="agreements", verbose_name="المورد")
    agreement_type = models.CharField("نوع الاتفاقية", max_length=20, choices=AGREEMENT_TYPES, default="blanket")
    status = models.CharField("الحالة", max_length=15, choices=STATUS, default="draft")
    start_date = models.DateField("تاريخ البدء", null=True, blank=True)
    end_date = models.DateField("تاريخ الانتهاء", null=True, blank=True)

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} - {self.supplier.name}"


class SupplierPricelist(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="supplier_pricelists")
    supplier = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="pricelists", verbose_name="المورد")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="supplier_pricelists", verbose_name="المنتج")
    min_qty = models.DecimalField("الحد الأدنى للكمية", max_digits=14, decimal_places=3, default=Decimal("1"))
    price = models.DecimalField("السعر", max_digits=14, decimal_places=2)
    currency = models.CharField("العملة", max_length=10, default="EGP")

    class Meta:
        ordering = ["supplier", "product"]

    def __str__(self):
        return f"{self.supplier.name} - {self.product.name} ({self.price})"


class PurchaseOrder(TimeStampedModel):
    STATUS = [
        ("draft", "جديد / طلب عرض سعر"),
        ("sent", "تم إرسال طلب عرض السعر"),
        ("late_rfq", "طلب عرض سعر متأخر"),
        ("unconfirmed", "غير معترف به"),
        ("confirmed", "أمر شراء مؤكد"),
        ("late_delivery", "إيصال متأخر"),
        ("received", "تم الاستلام"),
        ("cancel", "ملغى")
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_orders")
    number = models.CharField("الرقم المرجعي", max_length=30)
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="purchase_orders", verbose_name="المورد")
    purchaser = models.CharField("المشتري", max_length=100, blank=True, default="المسؤول")
    status = models.CharField("الحالة", max_length=20, choices=STATUS, default="draft")
    agreement = models.ForeignKey(PurchaseAgreement, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders", verbose_name="الاتفاقية")
    
    order_deadline = models.DateTimeField("الموعد النهائي للطلب", null=True, blank=True)
    expected_arrival = models.DateTimeField("الوصول المتوقع", null=True, blank=True)
    destination_warehouse = models.ForeignKey(Warehouse, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="التوصيل إلى")
    payment_terms = models.CharField("شروط السداد", max_length=100, blank=True)
    tax_included = models.BooleanField("شامل الضريبة", default=False)

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def total(self):
        base_total = sum((l.subtotal for l in self.lines.all()), Decimal("0"))
        if self.tax_included:
            return base_total
        return base_total * Decimal("1.14") # 14% VAT default calculation

    @property
    def subtotal_untaxed(self):
        return sum((l.subtotal for l in self.lines.all()), Decimal("0"))


class PurchaseLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_lines", verbose_name="المنتج")
    description = models.CharField("الوصف", max_length=200, blank=True)
    qty = models.DecimalField("الكمية", max_digits=14, decimal_places=3, default=Decimal("1"))
    cost = models.DecimalField("سعر الوحدة", max_digits=14, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField("الخصم %", max_digits=5, decimal_places=2, default=Decimal("0"))

    @property
    def subtotal(self):
        base = self.qty * self.cost
        if self.discount > 0:
            return base * (1 - (self.discount / Decimal("100")))
        return base
