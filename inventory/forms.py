from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "barcode", "unit", "sale_price", "cost", "min_qty"]
        labels = {"code": "الكود", "name": "الاسم", "barcode": "الباركود", "unit": "الوحدة",
                  "sale_price": "سعر البيع", "cost": "تكلفة الوحدة", "min_qty": "حد إعادة الطلب"}
        widgets = {"barcode": forms.TextInput(attrs={"autocomplete": "off"})}

    def _taken(self, field, value):
        qs = Product.objects.filter(company_id=self.instance.company_id, **{field: value})
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.exists()

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if self._taken("code", code):
            raise forms.ValidationError("الكود ده موجود قبل كده")
        return code

    def clean_barcode(self):
        barcode = (self.cleaned_data.get("barcode") or "").strip()
        if barcode and self._taken("barcode", barcode):
            raise forms.ValidationError("الباركود ده مربوط بصنف تاني")
        return barcode
