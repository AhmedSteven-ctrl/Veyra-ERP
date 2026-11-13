from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from core.forms import CompanyModelForm, OrderLineForm
from core.models import Partner
from inventory.models import Product

from .models import (PurchaseAgreement, PurchaseAgreementLine, PurchaseLine, PurchaseOrder, PurchasePayment,
                     SupplierPrice)
from .services import best_supplier_price


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "expected_date", "notes"]
        labels = {"supplier": "المورد", "expected_date": "تاريخ الاستلام المتوقع", "notes": "ملاحظات"}
        widgets = {
            "expected_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Partner.objects.filter(company=company, kind__in=["supplier", "both"])


class PurchasePaymentForm(forms.ModelForm):
    """دفعة للمورد. المبلغ الافتراضي هو المتبقي كله، ومينفعش يزيد عنه."""

    class Meta:
        model = PurchasePayment
        fields = ["amount", "method", "note"]
        labels = {"amount": "المبلغ", "method": "طريقة الدفع", "note": "ملاحظة"}

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        if order is not None:
            self.fields["amount"].label = f"المبلغ (المتبقي {order.balance})"
            self.fields["amount"].initial = order.balance

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("المبلغ لازم يكون أكبر من صفر")
        if self.order is not None and amount > self.order.balance:
            raise forms.ValidationError(f"المبلغ أكبر من المتبقي للمورد ({self.order.balance})")
        return amount


class PurchaseLineForm(OrderLineForm):
    """سطر أمر شراء. لو التكلفة فاضية: سعر المورد من قايمة الأسعار (لو متسجّل)، وإلا تكلفة الصنف."""
    price_field = "cost"
    price_default_from = "cost"

    class Meta:
        model = PurchaseLine
        fields = ["product", "qty", "cost"]
        labels = {"product": "الصنف", "qty": "الكمية", "cost": "التكلفة"}

    def __init__(self, *args, supplier_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.supplier_id = supplier_id

    def default_price(self, product, qty):
        if self.supplier_id:
            price = best_supplier_price(self.company, self.supplier_id, product, qty or Decimal("1"))
            if price is not None:
                return price
        return product.cost


PurchaseLineFormSet = inlineformset_factory(PurchaseOrder, PurchaseLine, form=PurchaseLineForm, extra=1,
                                            min_num=1, validate_min=True, can_delete=True)


class VendorForm(CompanyModelForm):
    """مورد (جهة اتصال نوعها مورد أو عميل ومورد)."""

    class Meta:
        model = Partner
        fields = ["name", "kind", "phone", "city"]
        labels = {"name": "الاسم", "kind": "النوع", "phone": "الهاتف", "city": "المدينة"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [("supplier", "مورد"), ("both", "عميل ومورد")]


class SupplierPriceForm(CompanyModelForm):
    class Meta:
        model = SupplierPrice
        fields = ["supplier", "product", "min_qty", "price", "valid_from", "valid_to"]
        labels = {"supplier": "المورد", "product": "الصنف", "min_qty": "أقل كمية", "price": "السعر",
                  "valid_from": "ساري من", "valid_to": "ساري لحد"}
        widgets = {"valid_from": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "valid_to": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Partner.objects.filter(company=self.company, kind__in=["supplier", "both"])
        self.fields["product"].queryset = Product.objects.filter(company=self.company)

    def clean(self):
        data = super().clean()
        min_qty, price = data.get("min_qty"), data.get("price")
        if min_qty is not None and min_qty <= 0:
            self.add_error("min_qty", "أقل كمية لازم تكون أكبر من صفر")
        if price is not None and price < 0:
            self.add_error("price", "السعر مينفعش يكون بالسالب")
        start, end = data.get("valid_from"), data.get("valid_to")
        if start and end and end < start:
            self.add_error("valid_to", "تاريخ النهاية قبل تاريخ البداية")
        return data


class AgreementForm(CompanyModelForm):
    class Meta:
        model = PurchaseAgreement
        fields = ["supplier", "start_date", "end_date", "notes"]
        labels = {"supplier": "المورد", "start_date": "تاريخ البداية", "end_date": "تاريخ النهاية", "notes": "ملاحظات"}
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Partner.objects.filter(company=self.company, kind__in=["supplier", "both"])

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "تاريخ النهاية قبل تاريخ البداية")
        return data


class AgreementLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseAgreementLine
        fields = ["product", "qty", "price"]
        labels = {"product": "الصنف", "qty": "الكمية المتفق عليها", "price": "السعر المتفق عليه"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(company=company)

    def clean(self):
        data = super().clean()
        qty, price = data.get("qty"), data.get("price")
        if qty is not None and qty <= 0:
            self.add_error("qty", "الكمية لازم تكون أكبر من صفر")
        if price is not None and price < 0:
            self.add_error("price", "السعر مينفعش يكون بالسالب")
        return data


AgreementLineFormSet = inlineformset_factory(PurchaseAgreement, PurchaseAgreementLine, form=AgreementLineForm,
                                             extra=1, min_num=1, validate_min=True, can_delete=True)
