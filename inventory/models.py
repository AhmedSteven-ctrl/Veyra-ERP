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


class ProductCategory(TimeStampedModel):
    """فئة منتجات (ممكن تتفرع: أغذية ← مجمدات)."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="product_categories")
    name = models.CharField("الاسم", max_length=100)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children",
                               verbose_name="الفئة الأم")

    class Meta:
        unique_together = [("company", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts, node, seen = [self.name], self.parent, {self.pk}
        while node is not None and node.pk not in seen:
            parts.append(node.name)
            seen.add(node.pk)
            node = node.parent
        return " / ".join(reversed(parts))


class ProductAttribute(TimeStampedModel):
    """خاصية للمنتجات (اللون، المقاس...) وليها قيم."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="product_attributes")
    name = models.CharField("الاسم", max_length=100)

    class Meta:
        unique_together = [("company", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductAttributeValue(TimeStampedModel):
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="values")
    name = models.CharField("القيمة", max_length=100)

    class Meta:
        unique_together = [("attribute", "name")]
        ordering = ["attribute__name", "name"]

    def __str__(self):
        return f"{self.attribute.name}: {self.name}"


class Product(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="products")
    code = models.CharField("الكود", max_length=40)
    name = models.CharField("الاسم", max_length=150)
    barcode = models.CharField("الباركود", max_length=64, blank=True, default="")
    category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="products", verbose_name="الفئة")
    attribute_values = models.ManyToManyField(ProductAttributeValue, blank=True, related_name="products",
                                              verbose_name="الخصائص")
    unit = models.CharField("الوحدة", max_length=20, default="قطعة")
    min_qty = models.DecimalField("حد إعادة الطلب", max_digits=14, decimal_places=3, default=Decimal("0"))
    sale_price = models.DecimalField("سعر البيع", max_digits=14, decimal_places=2, default=Decimal("0"))
    cost = models.DecimalField("تكلفة الوحدة", max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        unique_together = [("company", "code")]
        ordering = ["name"]
        constraints = [
            # الباركود فريد جوه الشركة (الفاضي مسموح يتكرر)
            models.UniqueConstraint(fields=["company", "barcode"], condition=~models.Q(barcode=""),
                                    name="uniq_product_barcode_per_company"),
        ]

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


class Uom(TimeStampedModel):
    """وحدة قياس (قطعة، كجم، متر...). المعامل = قيمتها مقارنة بوحدة المجموعة الأساسية (كجم=1، جرام=0.001، طن=1000)."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="uoms")
    name = models.CharField("الاسم", max_length=40)
    group = models.CharField("المجموعة", max_length=60, blank=True)
    ratio = models.DecimalField("المعامل", max_digits=14, decimal_places=6, default=Decimal("1"))

    class Meta:
        unique_together = [("company", "name")]
        ordering = ["group", "name"]

    def __str__(self):
        return self.name


class Packaging(TimeStampedModel):
    """تغليف لصنف (كرتونة = 12 قطعة)، وممكن يكون ليه باركود."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="packagings")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="packagings")
    name = models.CharField("الاسم", max_length=60)
    qty = models.DecimalField("الكمية في العبوة", max_digits=14, decimal_places=3, default=Decimal("1"))
    barcode = models.CharField("الباركود", max_length=64, blank=True, default="")

    class Meta:
        unique_together = [("product", "name")]
        ordering = ["product__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "barcode"], condition=~models.Q(barcode=""),
                                    name="uniq_packaging_barcode_per_company"),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name}"
