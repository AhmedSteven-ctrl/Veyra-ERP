from .models import CompanyModule, Module

# اسم الشاشة (URL) -> كود المديول الرئيسي
URL_MODULE = {
    "product_list": "inventory", "product_detail": "inventory", "product_create": "inventory",
    "sales_orders": "sales", "sales_detail": "sales", "sales_create": "sales", "sales_edit": "sales",
    "purchase_orders": "purchasing", "purchase_detail": "purchasing", "purchase_create": "purchasing",
    "purchase_edit": "purchasing",
    "partner_list": "contacts", "partner_create": "contacts", "partner_edit": "contacts",
    "settings_index": "settings", "settings_module": "settings",
    "journal_list": "accounting", "trial_balance": "accounting",
}


def module_nav(request):
    """يجيب المديولات الفرعية للمديول اللي إنت فيه، عشان تظهر جوه شريط المديول فوق."""
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if not user or not user.is_authenticated or not user.company_id or not match:
        return {"subs": []}
    code = URL_MODULE.get(match.url_name)
    if not code:
        return {"subs": []}
    enabled = set(CompanyModule.objects.filter(company_id=user.company_id, enabled=True)
                  .values_list("module__code", flat=True))
    subs = [m for m in Module.objects.filter(parent__code=code) if m.code in enabled and user.can_access(m.code)]
    return {"subs": subs, "current_module": code}
