from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "unit", "sale_price", "cost", "min_qty"]
        labels = {"code": "الكود", "name": "الاسم", "unit": "الوحدة",
                  "sale_price": "سعر البيع", "cost": "تكلفة الوحدة", "min_qty": "حد إعادة الطلب"}
