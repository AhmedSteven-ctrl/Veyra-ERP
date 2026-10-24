from django import forms
from django.forms import inlineformset_factory

from core.models import Partner
from inventory.models import Product

from .models import PurchaseLine, PurchaseOrder


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier"]
        labels = {"supplier": "المورد"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Partner.objects.filter(company=company, kind__in=["supplier", "both"])


class PurchaseLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseLine
        fields = ["product", "qty", "cost"]
        labels = {"product": "الصنف", "qty": "الكمية", "cost": "التكلفة"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(company=company)


PurchaseLineFormSet = inlineformset_factory(PurchaseOrder, PurchaseLine, form=PurchaseLineForm, extra=1, can_delete=True)
