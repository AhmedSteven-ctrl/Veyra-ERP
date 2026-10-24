from django import forms
from django.forms import inlineformset_factory

from core.models import Partner
from inventory.models import Product

from .models import SalesLine, SalesOrder


class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ["customer"]
        labels = {"customer": "العميل"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Partner.objects.filter(company=company, kind__in=["customer", "both"])


class SalesLineForm(forms.ModelForm):
    class Meta:
        model = SalesLine
        fields = ["product", "qty", "price"]
        labels = {"product": "الصنف", "qty": "الكمية", "price": "السعر"}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(company=company)


SalesLineFormSet = inlineformset_factory(SalesOrder, SalesLine, form=SalesLineForm, extra=1, can_delete=True)
