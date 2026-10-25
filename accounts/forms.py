from django import forms

from .models import UserProfile

DAYS = [("5", "السبت"), ("6", "الأحد"), ("0", "الاثنين"), ("1", "الثلاثاء"), ("2", "الأربعاء"), ("3", "الخميس"), ("4", "الجمعة")]


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["language", "theme", "notify_email", "email_signature"]
        labels = {"language": "اللغة", "theme": "الوضع", "notify_email": "إشعارات بالإيميل",
                  "email_signature": "توقيع الإيميل"}
        widgets = {"email_signature": forms.Textarea(attrs={"rows": 3})}


class CalendarForm(forms.ModelForm):
    work_days_list = forms.MultipleChoiceField(label="أيام العمل", choices=DAYS, required=False,
                                               widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = UserProfile
        fields = ["timezone", "work_location"]
        labels = {"timezone": "المنطقة الزمنية", "work_location": "مكان العمل"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["work_days_list"].initial = self.instance.work_days.split(",") if self.instance.work_days else []

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.work_days = ",".join(self.cleaned_data.get("work_days_list") or [])
        if commit:
            obj.save()
        return obj


class PrivateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["phone", "private_address", "birth_date", "emergency_name", "emergency_phone"]
        labels = {"phone": "الهاتف المحمول", "private_address": "العنوان الخاص", "birth_date": "تاريخ الميلاد",
                  "emergency_name": "اسم جهة الاتصال للطوارئ", "emergency_phone": "هاتف الطوارئ"}
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}
