from django.conf import settings
from django.db import models

from core.models import Company, TimeStampedModel


class Account(TimeStampedModel):
    TYPES = [("asset", "أصل"), ("liability", "التزام"), ("equity", "حقوق ملكية"),
             ("income", "إيراد"), ("expense", "مصروف")]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="accounts")
    code = models.CharField("الكود", max_length=10)
    name = models.CharField("الاسم", max_length=100)
    type = models.CharField("النوع", max_length=10, choices=TYPES)

    class Meta:
        unique_together = [("company", "code")]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


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
