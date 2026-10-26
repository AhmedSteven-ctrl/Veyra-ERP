from django import forms

from inventory.models import Product

from .models import Partner


class PartnerForm(forms.ModelForm):
    class Meta:
        model = Partner
        fields = ["name", "kind", "phone", "city"]
        labels = {"name": "الاسم", "kind": "النوع", "phone": "الهاتف", "city": "المدينة"}


from django.contrib.auth.forms import AuthenticationForm  # noqa: E402


class VeyraLoginForm(AuthenticationForm):
    username = forms.CharField(label="اسم المستخدم", widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    password = forms.CharField(label="كلمة المرور", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "اسم المستخدم أو كلمة المرور غير صحيحة.",
        "inactive": "الحساب ده موقوف.",
    }


class OrderLineForm(forms.ModelForm):
    """سطر في أمر بيع أو شراء: الصنف بالاختيار أو بمسح الباركود، والسعر الافتراضي بيتاخد من الصنف.
    الفورم اللي بيورّث منه لازم يحدد Meta (الموديل والحقول) واسم حقل السعر ومصدره في الصنف."""
    barcode = forms.CharField(label="باركود", required=False,
                              widget=forms.TextInput(attrs={"placeholder": "امسح الباركود", "autocomplete": "off"}))
    field_order = ["barcode", "product", "qty"]
    price_field = "price"            # اسم حقل السعر في السطر
    price_default_from = "sale_price"  # حقل الصنف اللي منه السعر لو سيبته فاضي

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["product"].queryset = Product.objects.filter(company=company)
        self.fields["product"].required = False   # ممكن الصنف يتحدد بالباركود بدل الاختيار
        self.fields[self.price_field].required = False

    def clean(self):
        data = super().clean()
        barcode = (data.get("barcode") or "").strip()
        product = data.get("product")
        if barcode:
            found = Product.objects.filter(company=self.company, barcode=barcode).first()
            if found is None:
                self.add_error("barcode", "مفيش صنف بالباركود ده")
                return data
            if product and product.pk != found.pk:
                self.add_error("barcode", "الباركود ده لصنف تاني غير اللي اخترته")
                return data
            product = data["product"] = found
        if product is None:
            if "product" not in self.errors:
                self.add_error("product", "اختار صنف أو امسح الباركود")
            return data
        qty = data.get("qty")
        if qty is not None and qty <= 0:
            self.add_error("qty", "الكمية لازم تكون أكبر من صفر")
        price = data.get(self.price_field)
        if price is None and self.price_field not in self.errors:
            data[self.price_field] = getattr(product, self.price_default_from)
        elif price is not None and price < 0:
            self.add_error(self.price_field, "السعر مينفعش يكون بالسالب")
        return data
