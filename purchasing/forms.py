from django import forms
from django.forms import inlineformset_factory

from core.forms import OrderLineForm
from core.models import Partner

from .models import PurchaseLine, PurchaseOrder, PurchasePayment


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
    price_field = "cost"
    price_default_from = "cost"

    class Meta:
        model = PurchaseLine
        fields = ["product", "qty", "cost"]
        labels = {"product": "الصنف", "qty": "الكمية", "cost": "التكلفة"}


PurchaseLineFormSet = inlineformset_factory(PurchaseOrder, PurchaseLine, form=PurchaseLineForm, extra=1,
                                            min_num=1, validate_min=True, can_delete=True)
