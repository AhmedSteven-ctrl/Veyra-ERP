import re

from django import forms

from core.forms import CompanyModelForm

from .chart import broad_type, default_nature, default_statement, descendant_ids, role_usage, suggest_parent
from .models import Account, AccountMapping


class AccountForm(CompanyModelForm):
    unique_per_company = ("code",)

    class Meta:
        model = Account
        fields = ["code", "name", "kind", "parent", "nature", "statement", "is_group", "is_active", "description"]
        labels = {"code": "الكود", "name": "اسم الحساب", "kind": "نوع الحساب", "parent": "الحساب الرئيسي",
                  "nature": "الطبيعة", "statement": "القائمة المالية", "is_group": "تجميعي (لا يقبل قيود)",
                  "is_active": "نشط", "description": "الوصف"}
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = Account.objects.filter(company=self.company).order_by("code")
        if self.instance.pk:  # مينفعش الحساب يبقى تابع لنفسه أو لحاجة تحته
            parents = parents.exclude(pk__in={self.instance.pk} | descendant_ids(self.instance))
        self.fields["parent"].queryset = parents
        self.fields["parent"].required = False
        self.fields["parent"].label_from_instance = lambda a: f"{a.code} {a.name}"

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not re.fullmatch(r"\d{3,10}", code):
            raise forms.ValidationError("الكود لازم أرقام فقط (من 3 إلى 10 خانات)")
        if self.instance.pk and code != self.instance.code and self.instance.lines.exists():
            raise forms.ValidationError("الحساب عليه قيود فمينفعش تغيّر كوده")
        return code

    def clean(self):
        data = super().clean()
        code, kind = data.get("code"), data.get("kind")
        if code and kind:
            broad = broad_type(kind, code)
            if not data.get("nature"):
                data["nature"] = default_nature(broad)
            if not data.get("statement"):
                data["statement"] = default_statement(broad)
        account = self.instance if self.instance.pk else None
        if account is not None:
            if data.get("is_group") and not account.is_group and account.lines.exists():
                self.add_error("is_group", "الحساب عليه قيود فمينفعش يتحول لتجميعي")
            if (data.get("is_group") and not account.is_group) or (not data.get("is_active", True) and account.is_active):
                usage = role_usage(account)
                if usage:
                    field = "is_group" if data.get("is_group") else "is_active"
                    self.add_error(field, "مستخدم كحساب افتراضي: " + "، ".join(usage)
                                   + ". غيّره من «الحسابات الافتراضية» الأول")
        elif code and not data.get("parent"):  # حساب جديد من غير أب: نقترح الأقرب بالكود
            groups = dict(Account.objects.filter(company=self.company).values_list("code", "is_group"))
            suggested = suggest_parent(code, groups, five_digit_rule=False)
            if suggested:
                data["parent"] = Account.objects.get(company=self.company, code=suggested)
        return data

    def save(self, commit=True):
        account = super().save(commit=False)
        account.type = broad_type(account.kind, account.code)
        if commit:
            account.save()
        return account


class AccountRolesForm(forms.Form):
    """حساب لكل دور. القيود التلقائية (مبيعات، مشتريات، مدفوعات) بتستخدم الحسابات دي."""

    def __init__(self, *args, company=None, current=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        postable = Account.objects.filter(company=company, is_group=False, is_active=True).order_by("code")
        for role, label in AccountMapping.ROLES:
            field = forms.ModelChoiceField(label=label, queryset=postable, required=True)
            field.label_from_instance = lambda a: f"{a.code} {a.name}"
            if current and role in current:
                field.initial = current[role].pk
            self.fields[role] = field

    def save(self):
        for role, _label in AccountMapping.ROLES:
            AccountMapping.objects.update_or_create(company=self.company, role=role,
                                                    defaults={"account": self.cleaned_data[role]})


class AccountImportForm(forms.Form):
    file = forms.FileField(label="ملف CSV (نفس أعمدة التصدير)")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError("الملف أكبر من 2 ميجا")
        try:
            return upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError("الملف لازم يكون UTF-8 (احفظه من Excel كـ CSV UTF-8)")
