from django import forms

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
