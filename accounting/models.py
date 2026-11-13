from django.conf import settings
from django.db import models

from core.models import Company, TimeStampedModel


class Account(TimeStampedModel):
    """حساب في دليل الحسابات. الدليل الافتراضي (نمط Odoo) في chart_data.py، والمستخدم يقدر يضيف ويعدّل ويوقف."""
    TYPES = [("asset", "أصل"), ("liability", "التزام"), ("equity", "حقوق ملكية"),
             ("income", "إيراد"), ("expense", "مصروف")]
    KINDS = [
        ("view", "حساب تجميعي (View)"), ("fixed_asset", "أصول ثابتة"), ("current_asset", "أصول متداولة"),
        ("receivable", "ذمم مدينة (عملاء)"), ("bank_cash", "بنك ونقدية"), ("prepayment", "مدفوعات مقدمة"),
        ("payable", "ذمم دائنة (موردين)"), ("current_liability", "التزامات جارية"),
        ("non_current_liability", "التزامات غير جارية"), ("equity", "حقوق ملكية"), ("income", "إيرادات"),
        ("other_income", "إيرادات أخرى"), ("cost_of_revenue", "تكلفة الإيرادات"), ("expense", "مصروفات"),
        ("depreciation", "إهلاك"),
    ]
    NATURES = [("debit", "مدين"), ("credit", "دائن")]
    STATEMENTS = [("balance_sheet", "المركز المالي"), ("income_statement", "قائمة الدخل")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="accounts")
    code = models.CharField("الكود", max_length=10)
    name = models.CharField("الاسم", max_length=150)
    type = models.CharField("التصنيف", max_length=10, choices=TYPES)
    kind = models.CharField("نوع الحساب", max_length=25, choices=KINDS, default="current_asset")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children",
                               verbose_name="الحساب الرئيسي")
    nature = models.CharField("الطبيعة", max_length=6, choices=NATURES, default="debit")
    statement = models.CharField("القائمة المالية", max_length=16, choices=STATEMENTS, default="balance_sheet")
    description = models.CharField("الوصف", max_length=255, blank=True)
    is_group = models.BooleanField("تجميعي (لا يقبل قيود)", default=False)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        unique_together = [("company", "code")]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class AccountMapping(TimeStampedModel):
    """الحساب الافتراضي لكل دور (العملاء، الموردين، المخزون...). القيود التلقائية بتستخدمه بدل أكواد ثابتة."""
    ROLES = [
        ("receivable", "حساب العملاء"), ("payable", "حساب الموردين"), ("inventory", "حساب المخزون"),
        ("vat_input", "ضريبة المدخلات (المشتريات)"), ("vat_output", "ضريبة المخرجات (المبيعات)"),
        ("sales", "إيرادات المبيعات"), ("cogs", "تكلفة البضاعة المباعة"),
        ("cash", "النقدية (الخزينة)"), ("bank", "البنك"),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="account_mappings")
    role = models.CharField(max_length=20, choices=ROLES)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="mappings")

    class Meta:
        unique_together = [("company", "role")]

    def __str__(self):
        return f"{self.get_role_display()} ← {self.account}"


class Journal(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="journals")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = [("company", "code")]

    def __str__(self):
        return self.name


class JournalEntry(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="entries")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name="entries")
    date = models.DateField(auto_now_add=True)
    reference = models.CharField("المرجع", max_length=60)
    memo = models.CharField("البيان", max_length=200, blank=True)
    posted = models.BooleanField("مرحّل", default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
