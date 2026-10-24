from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "unit", "sale_price", "min_qty"]
        labels = {"code": "الكود", "name": "الاسم", "unit": "الوحدة",
                  "sale_price": "سعر البيع", "min_qty": "حد إعادة الطلب"}
