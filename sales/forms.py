from django import forms
from django.forms import inlineformset_factory

from core.forms import OrderLineForm
from core.models import Partner

from .models import SalesLine, SalesOrder


class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ["customer"]
        labels = {"customer": "العميل"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Partner.objects.filter(company=company, kind__in=["customer", "both"])


class SalesLineForm(OrderLineForm):
    price_field = "price"
    price_default_from = "sale_price"

    class Meta:
        model = SalesLine
        fields = ["product", "qty", "price"]
        labels = {"product": "الصنف", "qty": "الكمية", "price": "السعر"}


SalesLineFormSet = inlineformset_factory(SalesOrder, SalesLine, form=SalesLineForm, extra=1,
                                         min_num=1, validate_min=True, can_delete=True)
