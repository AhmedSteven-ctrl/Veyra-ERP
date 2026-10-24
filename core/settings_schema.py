"""إعدادات كل مديول مقسمة لمجموعات (زي شاشة الإعدادات في أودو).
كل حقل: (المفتاح، الاسم، النوع، الافتراضي، الاختيارات، المجموعة).
الأفكار مأخوذة من إعدادات أودو في الصور، ومن الشيت (الترقيم، الحدود، الضرايب، الإقفال، الباركود)."""
from decimal import Decimal

from django import forms

from .models import ModuleSetting

SCHEMA = {
    "sales": [
        ("prefix", "بادئة أمر البيع", "text", "SO", None, "أوامر البيع"),
        ("approval", "موافقة مدير على أمر البيع فوق حد", "bool", True, None, "أوامر البيع"),
        ("approval_amount", "الحد اللي فوقه يحتاج موافقة", "decimal", Decimal("5000"), None, "أوامر البيع"),
        ("lock_confirmed", "قفل الأوامر المؤكدة (منع التعديل)", "bool", True, None, "أوامر البيع"),
        ("quote_validity", "مدة صلاحية عرض السعر (يوم)", "int", 30, None, "أوامر البيع"),
        ("tax_rate", "نسبة الضريبة %", "decimal", Decimal("14"), None, "الفواتير"),
        ("invoice_numbering", "ترقيم الفواتير", "choice", "auto", [("auto", "تلقائي"), ("manual", "يدوي")], "الفواتير"),
        ("e_sign", "توقيع إلكتروني على عروض الأسعار", "bool", False, None, "الفواتير"),
        ("discounts", "الخصومات على البنود", "bool", True, None, "الأسعار"),
        ("price_lists", "قوائم أسعار متعددة لكل عميل", "bool", False, None, "الأسعار"),
    ],
    "purchasing": [
        ("prefix", "بادئة أمر الشراء", "text", "PO", None, "أوامر الشراء"),
        ("min_quotes", "أقل عدد عروض أسعار قبل الشراء", "int", 3, None, "أوامر الشراء"),
        ("approval", "موافقة على أمر الشراء فوق حد", "bool", True, None, "أوامر الشراء"),
        ("approval_amount", "الحد الأدنى للموافقة (ج.م)", "decimal", Decimal("5000"), None, "أوامر الشراء"),
        ("pay_after_receipt", "الدفع بعد الاستلام فقط", "bool", True, None, "الاستلام والفواتير"),
        ("three_way", "المطابقة الثلاثية (أمر + استلام + فاتورة)", "bool", True, None, "الاستلام والفواتير"),
        ("receipt_reminder", "تذكير المورد بتاريخ الاستلام", "bool", True, None, "الاستلام والفواتير"),
        ("variants", "متغيرات المنتج (مقاس، لون)", "bool", False, None, "المنتجات"),
    ],
    "inventory": [
        ("valuation", "طريقة تقييم المخزون", "choice", "avg", [("avg", "متوسط مرجح"), ("fifo", "FIFO")], "التقييم"),
        ("allow_negative", "السماح بالرصيد السالب", "bool", False, None, "التقييم"),
        ("low_alert", "تنبيه تحت حد إعادة الطلب", "bool", True, None, "التقييم"),
        ("barcode", "قراءة الباركود", "bool", True, None, "الباركود والمواقع"),
        ("locations", "مواقع داخل كل مخزن (رف، صف)", "bool", True, None, "الباركود والمواقع"),
        ("multi_step", "مسارات استلام وتسليم متعددة الخطوات", "bool", False, None, "الباركود والمواقع"),
        ("expiry", "تتبع تاريخ الصلاحية", "bool", False, None, "الدفعات والأرقام"),
        ("serial", "أرقام تسلسلية للأصناف", "bool", False, None, "الدفعات والأرقام"),
        ("lot", "تتبع الدفعات (Lots)", "bool", False, None, "الدفعات والأرقام"),
    ],
    "accounting": [
        ("currency", "العملة الرئيسية", "text", "EGP", None, "العملة والسنة"),
        ("fiscal_start", "بداية السنة المالية (رقم الشهر)", "int", 1, None, "العملة والسنة"),
        ("lock_closed", "منع الترحيل في الفترة المقفولة", "bool", True, None, "العملة والسنة"),
        ("default_tax", "ضريبة المبيعات الافتراضية %", "decimal", Decimal("14"), None, "الضرائب"),
        ("vat_method", "طريقة حساب الضريبة", "choice", "line", [("line", "لكل بند"), ("invoice", "على الفاتورة")], "الضرائب"),
        ("cash_basis", "الضرائب على أساس نقدي", "bool", False, None, "الضرائب"),
        ("e_invoice", "الفاتورة الإلكترونية", "bool", False, None, "الفواتير والتقارير"),
        ("monthly_reconcile", "تسوية بنكية شهرية إلزامية", "bool", True, None, "الفواتير والتقارير"),
        ("audit_log", "سجل مراجعة للقيود", "bool", True, None, "الفواتير والتقارير"),
    ],
    "contacts": [
        ("default_kind", "النوع الافتراضي لجهة الاتصال", "choice", "customer",
         [("customer", "عميل"), ("supplier", "مورد"), ("both", "عميل ومورد")], "جهات الاتصال"),
        ("vip", "علامة VIP للعملاء المميزين", "bool", True, None, "جهات الاتصال"),
        ("customer_types", "أنواع العملاء", "bool", True, None, "جهات الاتصال"),
        ("lead_assign", "توزيع العملاء المحتملين", "choice", "manual",
         [("manual", "يدوي"), ("round_robin", "بالتناوب"), ("region", "حسب المنطقة")], "CRM"),
        ("lead_sla", "مدة الرد على العميل المحتمل (ساعة)", "int", 24, None, "CRM"),
        ("whatsapp", "إرسال الرسائل عبر واتساب", "bool", True, None, "التواصل"),
    ],
    "employees": [
        ("work_days", "أيام العمل في الأسبوع", "int", 6, None, "الدوام"),
        ("overtime_rate", "معامل الساعات الإضافية", "decimal", Decimal("1.5"), None, "الدوام"),
        ("device", "ربط جهاز البصمة", "bool", False, None, "الدوام"),
        ("annual_leave", "أيام الإجازة السنوية", "int", 21, None, "الإجازات"),
        ("leave_approval", "اعتماد المدير المباشر للإجازة", "bool", True, None, "الإجازات"),
    ],
    "settings": [
        ("company_name", "اسم الشركة", "text", "شركة النور للتجارة", None, "الشركة"),
        ("language", "اللغة الافتراضية", "choice", "ar", [("ar", "العربية"), ("en", "English")], "اللغة والمظهر"),
        ("theme", "الوضع الافتراضي", "choice", "light", [("light", "فاتح"), ("dark", "داكن")], "اللغة والمظهر"),
    ],
}


def _spec(field):
    return field[0], field[1], field[2], field[3], field[4], field[5]


def current_values(company, code):
    saved = dict(ModuleSetting.objects.filter(company=company, module=code).values_list("key", "value"))
    out = {}
    for field in SCHEMA.get(code, []):
        key, _label, kind, default, _choices, _group = _spec(field)
        if key in saved:
            raw = saved[key]
            if kind == "bool":
                out[key] = raw == "1"
            elif kind == "int":
                out[key] = int(raw or default)
            elif kind == "decimal":
                out[key] = Decimal(raw or str(default))
            else:
                out[key] = raw
        else:
            out[key] = default
    return out


def build_form(code, data=None, company=None):
    fields = {}
    initial = current_values(company, code) if company else {}
    for field in SCHEMA.get(code, []):
        key, label, kind, default, choices, _group = _spec(field)
        init = initial.get(key, default)
        if kind == "bool":
            fields[key] = forms.BooleanField(label=label, required=False, initial=init)
        elif kind == "int":
            fields[key] = forms.IntegerField(label=label, initial=init, min_value=0)
        elif kind == "decimal":
            fields[key] = forms.DecimalField(label=label, initial=init, min_value=Decimal("0"), max_digits=12, decimal_places=2)
        elif kind == "choice":
            fields[key] = forms.ChoiceField(label=label, choices=choices, initial=init)
        else:
            fields[key] = forms.CharField(label=label, initial=init, max_length=120)
    FormClass = type(f"{code.title()}SettingsForm", (forms.Form,), fields)
    return FormClass(data) if data is not None else FormClass()


def grouped(code, form):
    """يرجّع الحقول مجمعة حسب المجموعة بالترتيب: [(اسم المجموعة، [حقول])]."""
    order, buckets = [], {}
    group_of = {f[0]: f[5] for f in SCHEMA.get(code, [])}
    for bf in form:
        g = group_of.get(bf.name, "")
        if g not in buckets:
            buckets[g] = []
            order.append(g)
        buckets[g].append(bf)
    return [(g, buckets[g]) for g in order]


def save_values(company, code, cleaned):
    for key, value in cleaned.items():
        if isinstance(value, bool):
            value = "1" if value else "0"
        ModuleSetting.objects.update_or_create(company=company, module=code, key=key,
                                               defaults={"value": str(value)})
