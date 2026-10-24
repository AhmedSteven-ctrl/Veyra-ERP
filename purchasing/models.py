from decimal import Decimal

from django.db import models

from core.models import Company, Partner, TimeStampedModel
from inventory.models import Product


class PurchaseOrder(TimeStampedModel):
    STATUS = [("draft", "مسودة"), ("confirmed", "بانتظار الاستلام"), ("received", "مستلم")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_orders")
    number = models.CharField("الرقم", max_length=30)
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField("الحالة", max_length=12, choices=STATUS, default="confirmed")

    class Meta:
        unique_together = [("company", "number")]
        ordering = ["-created_at"]

    @property
    def total(self):
        return sum((l.subtotal for l in self.lines.all()), Decimal("0"))


class PurchaseLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_lines")
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    cost = models.DecimalField(max_digits=14, decimal_places=2)

    @property
    def subtotal(self):
        return self.qty * self.cost
