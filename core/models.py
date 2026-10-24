from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimeStampedModel):
    name = models.CharField("اسم الشركة", max_length=150)
    code = models.CharField("كود الشركة", max_length=20, unique=True)
    country = models.CharField("البلد", max_length=2, default="EG")
    currency = models.CharField("العملة", max_length=3, default="EGP")
    version = models.CharField("إصدار النظام", max_length=20, default="2.4.0")
    is_active = models.BooleanField("نشطة", default=True)

    def __str__(self):
        return self.name


class Module(TimeStampedModel):
    CATEGORY = [("main", "رئيسي"), ("sub", "فرعي")]

    code = models.SlugField("الكود", max_length=40, unique=True)
    name = models.CharField("الاسم", max_length=100)
    category = models.CharField("النوع", max_length=10, choices=CATEGORY, default="main")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="required_by")
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name


class CompanyModule(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="module_links")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="company_links")
    enabled = models.BooleanField(default=False)

    class Meta:
        unique_together = [("company", "module")]


class Partner(TimeStampedModel):
    KIND = [("customer", "عميل"), ("supplier", "مورد"), ("both", "عميل ومورد")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="partners")
    name = models.CharField("الاسم", max_length=150)
    kind = models.CharField("النوع", max_length=10, choices=KIND, default="customer")
    phone = models.CharField("الهاتف", max_length=30, blank=True)
    city = models.CharField("المدينة", max_length=60, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
