from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    company = models.ForeignKey("core.Company", null=True, blank=True,
                                on_delete=models.PROTECT, related_name="users")
    is_company_manager = models.BooleanField("مدير الشركة", default=False)
    allowed_modules = models.ManyToManyField("core.Module", blank=True, related_name="users")
    must_change_password = models.BooleanField("لازم يغيّر كلمة المرور", default=False)

    def accessible_codes(self):
        """أكواد المديولات اللي يقدر يفتحها (للشاشات اللي بتعرض قايمة): استعلامين بدل استعلام لكل مديول."""
        if not self.company_id:
            return set()
        from core.models import CompanyModule
        enabled = set(CompanyModule.objects.filter(company_id=self.company_id, enabled=True)
                      .values_list("module__code", flat=True))
        if self.is_superuser or self.is_company_manager:
            return enabled
        return enabled & set(self.allowed_modules.values_list("code", flat=True))

    def can_access(self, code):
        """المالك (superuser) يشوف كل حاجة. غير كده: المديول لازم يكون مفعّل للشركة،
        والمدير يشوف كل المفعّل، والمستخدم العادي يشوف اللي اتسمحله بس."""
        if self.is_superuser:
            return True
        if not self.company_id:
            return False
        from core.models import CompanyModule
        if not CompanyModule.objects.filter(company_id=self.company_id, module__code=code, enabled=True).exists():
            return False
        if self.is_company_manager:
            return True
        return self.allowed_modules.filter(code=code).exists()


class UserProfile(models.Model):
    """تفضيلات الحساب والمعلومات الشخصية (شاشة تفضيلاتي)."""
    THEME = [("light", "فاتح"), ("dark", "داكن"), ("system", "حسب الجهاز")]
    LANG = [("ar", "العربية"), ("en", "English")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    language = models.CharField("اللغة", max_length=5, choices=LANG, default="ar")
    theme = models.CharField("الوضع", max_length=10, choices=THEME, default="light")
    timezone = models.CharField("المنطقة الزمنية", max_length=40, default="Africa/Cairo")
    notify_email = models.BooleanField("إشعارات بالإيميل", default=True)
    email_signature = models.TextField("توقيع الإيميل", blank=True)
    work_location = models.CharField("مكان العمل", max_length=60, default="المكتب الرئيسي")
    work_days = models.CharField("أيام العمل", max_length=20, default="0,1,2,3,4,5")  # 0=السبت
    phone = models.CharField("الهاتف المحمول", max_length=30, blank=True)
    private_address = models.CharField("العنوان الخاص", max_length=200, blank=True)
    birth_date = models.DateField("تاريخ الميلاد", null=True, blank=True)
    emergency_name = models.CharField("اسم جهة الاتصال للطوارئ", max_length=100, blank=True)
    emergency_phone = models.CharField("هاتف الطوارئ", max_length=30, blank=True)
    two_factor = models.BooleanField("التحقق بخطوتين", default=False)

    def __str__(self):
        return f"تفضيلات {self.user}"
