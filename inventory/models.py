from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import Company, TimeStampedModel


class Warehouse(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="warehouses")
    code = models.CharField("الكود", max_length=20)
    name = models.CharField("الاسم", max_length=100)

    class Meta:
        unique_together = [("company", "code")]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="products")
    code = models.CharField("الكود", max_length=40)
    name = models.CharField("الاسم", max_length=150)
    unit = models.CharField("الوحدة", max_length=20, default="قطعة")
    min_qty = models.DecimalField("حد إعادة الطلب", max_digits=14, decimal_places=3, default=Decimal("0"))
    sale_price = models.DecimalField("سعر البيع", max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        unique_together = [("company", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockMove(TimeStampedModel):
    """دفتر حركات المخزن: الرصيد دايماً = مجموع الحركات. مفيش رقم بيتعدل بإيده."""
    KIND = [("receipt", "استلام"), ("issue", "صرف"), ("adjust", "تسوية")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_moves")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_moves")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_moves")
    qty = models.DecimalField("الكمية (+ دخول / - خروج)", max_digits=14, decimal_places=3)
    kind = models.CharField(max_length=10, choices=KIND)
    reference = models.CharField("المرجع", max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "product", "warehouse"])]
