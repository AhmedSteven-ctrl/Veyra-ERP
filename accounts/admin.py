from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class VeyraUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("الشركة والصلاحيات", {"fields": ("company", "is_company_manager", "allowed_modules", "must_change_password")}),
    )
