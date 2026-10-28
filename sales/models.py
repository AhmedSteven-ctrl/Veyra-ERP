from decimal import Decimal
from django.db import models
from core.models import Company, Partner, TimeStampedModel
from inventory.models import Product


class PriceList(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="pricelists")
    name = models.CharField("اسم قائمة الأسعار", max_length=100)
    discount_percentage = models.DecimalField("نسبة الخصم %", max_digits=5, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SalesOrder(TimeStampedModel):
    STATUS = [
        ("quote", "عرض سعر"),
        ("draft", "مسودة"),
        ("confirmed", "مؤكد"),
        ("delivered", "تم التسليم"),
        ("returned", "مرتجع بالكامل"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sales_orders")
    number = models.CharField("الرقم", max_length=30)
    customer = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="sales_orders")
    status = models.CharField("الحالة", max_length=15, choices=STATUS, default="draft")
    pricelist = models.ForeignKey(PriceList, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_orders", verbose_name="قائمة الأسعار")

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    @property
    def total(self):
        base_total = sum((l.subtotal for l in self.lines.all()), Decimal("0"))
        if self.pricelist and self.pricelist.discount_percentage > 0:
            discount = base_total * (self.pricelist.discount_percentage / Decimal("100"))
            return base_total - discount
        return base_total


class SalesLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sales_lines")
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    price = models.DecimalField(max_digits=14, decimal_places=2)

    @property
    def subtotal(self):
        return self.qty * self.price


class SalesReturn(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sales_returns")
    number = models.CharField("رقم المرتجع", max_length=30)
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="returns")
    reason = models.CharField("سبب الارتجاع", max_length=200, blank=True)

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    def __str__(self):
        return self.number
