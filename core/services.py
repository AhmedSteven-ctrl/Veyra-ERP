from .models import CompanyModule, Module


class ModuleDependencyError(Exception):
    pass


def enabled_codes(company):
    return set(CompanyModule.objects.filter(company=company, enabled=True).values_list("module__code", flat=True))


def missing_dependencies(company, module):
    enabled = enabled_codes(company)
    return [d for d in module.depends_on.all() if d.code not in enabled]


def set_module(company, module, enabled):
    """تفعيل أو تعطيل مديول لشركة مع التحقق من الاعتمادات بين المديولات."""
    if enabled:
        missing = missing_dependencies(company, module)
        if missing:
            names = "، ".join(m.name for m in missing)
            raise ModuleDependencyError(f"لازم تفعّل الأول: {names}")
    else:
        blocked = Module.objects.filter(
            depends_on=module,
            company_links__company=company,
            company_links__enabled=True,
        ).distinct()
        if blocked.exists():
            names = "، ".join(m.name for m in blocked)
            raise ModuleDependencyError(f"لازم تعطّل الأول: {names}")
    CompanyModule.objects.update_or_create(company=company, module=module, defaults={"enabled": enabled})
