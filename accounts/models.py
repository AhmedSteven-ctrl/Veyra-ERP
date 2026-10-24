from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    company = models.ForeignKey("core.Company", null=True, blank=True,
                                on_delete=models.PROTECT, related_name="users")
    is_company_manager = models.BooleanField("مدير الشركة", default=False)
    allowed_modules = models.ManyToManyField("core.Module", blank=True, related_name="users")

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
