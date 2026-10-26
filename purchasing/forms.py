from django import forms
from django.forms import inlineformset_factory

from core.forms import OrderLineForm
from core.models import Partner

from .models import PurchaseLine, PurchaseOrder


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier"]
        labels = {"supplier": "المورد"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Partner.objects.filter(company=company, kind__in=["supplier", "both"])


class PurchaseLineForm(OrderLineForm):
    price_field = "cost"
    price_default_from = "cost"

    class Meta:
        model = PurchaseLine
        fields = ["product", "qty", "cost"]
        labels = {"product": "الصنف", "qty": "الكمية", "cost": "التكلفة"}


PurchaseLineFormSet = inlineformset_factory(PurchaseOrder, PurchaseLine, form=PurchaseLineForm, extra=1,
                                            min_num=1, validate_min=True, can_delete=True)
