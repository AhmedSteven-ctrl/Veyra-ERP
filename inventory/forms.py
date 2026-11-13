from django import forms
from django.forms import inlineformset_factory

from core.forms import CompanyModelForm

from .models import (Packaging, Product, ProductAttribute, ProductAttributeValue, ProductCategory, Uom)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "barcode", "category", "unit", "sale_price", "cost", "min_qty", "attribute_values"]
        labels = {"code": "الكود", "name": "الاسم", "barcode": "الباركود", "category": "الفئة", "unit": "الوحدة",
                  "sale_price": "سعر البيع", "cost": "تكلفة الوحدة", "min_qty": "حد إعادة الطلب",
                  "attribute_values": "الخصائص"}
        widgets = {"barcode": forms.TextInput(attrs={"autocomplete": "off"}),
                   "attribute_values": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company_id = self.instance.company_id  # الفئات والخصائص بتاعة نفس الشركة بس
        self.fields["category"].queryset = ProductCategory.objects.filter(company_id=company_id)
        self.fields["category"].label_from_instance = lambda c: c.full_name
        self.fields["attribute_values"].queryset = (
            ProductAttributeValue.objects.filter(attribute__company_id=company_id).select_related("attribute"))
        self.fields["attribute_values"].label_from_instance = lambda v: f"{v.attribute.name}: {v.name}"

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


class CategoryForm(CompanyModelForm):
    unique_per_company = ("name",)

    class Meta:
        model = ProductCategory
        fields = ["name", "parent"]
        labels = {"name": "الاسم", "parent": "الفئة الأم"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = ProductCategory.objects.filter(company=self.company)
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parents
        self.fields["parent"].label_from_instance = lambda c: c.full_name

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        node, seen = parent, set()
        while node is not None and node.pk not in seen:
            if self.instance.pk and node.pk == self.instance.pk:
                raise forms.ValidationError("الفئة مينفعش تتبع نفسها أو أي فئة من فروعها")
            seen.add(node.pk)
            node = node.parent
        return parent


class AttributeForm(CompanyModelForm):
    unique_per_company = ("name",)

    class Meta:
        model = ProductAttribute
        fields = ["name"]
        labels = {"name": "اسم الخاصية"}


AttributeValueFormSet = inlineformset_factory(ProductAttribute, ProductAttributeValue, fields=["name"],
                                              labels={"name": "القيمة"}, extra=3, can_delete=True)


class UomForm(CompanyModelForm):
    unique_per_company = ("name",)

    class Meta:
        model = Uom
        fields = ["name", "group", "ratio"]
        labels = {"name": "اسم الوحدة", "group": "المجموعة (مثال: الوزن)", "ratio": "المعامل (مقارنة بوحدة المجموعة الأساسية)"}

    def clean_ratio(self):
        ratio = self.cleaned_data["ratio"]
        if ratio <= 0:
            raise forms.ValidationError("المعامل لازم يكون أكبر من صفر")
        return ratio


class PackagingForm(CompanyModelForm):
    unique_per_company = ("barcode",)

    class Meta:
        model = Packaging
        fields = ["product", "name", "qty", "barcode"]
        labels = {"product": "الصنف", "name": "اسم التغليف (مثال: كرتونة)", "qty": "الكمية في العبوة",
                  "barcode": "الباركود"}
        widgets = {"barcode": forms.TextInput(attrs={"autocomplete": "off"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(company=self.company)

    def clean_qty(self):
        qty = self.cleaned_data["qty"]
        if qty <= 0:
            raise forms.ValidationError("الكمية لازم تكون أكبر من صفر")
        return qty

    def clean_barcode(self):
        return (self.cleaned_data.get("barcode") or "").strip()

    def clean(self):
        data = super().clean()
        product, name = data.get("product"), (data.get("name") or "").strip()
        if product and name:
            same = Packaging.objects.filter(product=product, name=name)
            if self.instance.pk:
                same = same.exclude(pk=self.instance.pk)
            if same.exists():
                self.add_error("name", "الصنف ده عنده تغليف بنفس الاسم")
        return data
