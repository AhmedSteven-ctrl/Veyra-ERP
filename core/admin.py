from django.contrib import admin

from .models import Company, CompanyModule, Module, Partner


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "currency", "version", "is_active")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "category", "parent", "sort")
    filter_horizontal = ("depends_on",)


@admin.register(CompanyModule)
class CompanyModuleAdmin(admin.ModelAdmin):
    list_display = ("company", "module", "enabled")
    list_filter = ("company", "enabled")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "company", "city")
    list_filter = ("company", "kind")


from .models import ModuleSetting  # noqa: E402


@admin.register(ModuleSetting)
class ModuleSettingAdmin(admin.ModelAdmin):
    list_display = ("module", "key", "company", "value")
    list_filter = ("company", "module")
    search_fields = ("key",)
