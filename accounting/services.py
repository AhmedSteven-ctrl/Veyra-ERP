"""القيود المحاسبية من المبيعات والمشتريات.
كل قيد لازم يكون متوازن (مدين = دائن)، ومرة واحدة لكل مستند (مش بيتكرر لو اتعمل تاني)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from core.settings_schema import current_values

from .models import Account, Journal, JournalEntry, JournalLine

CHART = [
    ("1010", "النقدية والبنك", "asset"),
    ("1200", "العملاء", "asset"),
    ("1300", "المخزون", "asset"),
    ("1400", "ضريبة مدخلات", "asset"),
    ("2100", "الموردون", "liability"),
    ("2200", "ضريبة مخرجات", "liability"),
    ("4000", "إيرادات المبيعات", "income"),
    ("5000", "تكلفة البضاعة المباعة", "expense"),
]
JOURNALS = [("SAL", "يومية المبيعات"), ("PUR", "يومية المشتريات")]


def _money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_chart(company):
    for code, name, kind in CHART:
        Account.objects.get_or_create(company=company, code=code, defaults={"name": name, "type": kind})
    for code, name in JOURNALS:
        Journal.objects.get_or_create(company=company, code=code, defaults={"name": name})


def _post(company, journal_code, reference, memo, lines, user=None):
    ensure_chart(company)
    if JournalEntry.objects.filter(company=company, reference=reference, journal__code=journal_code).exists():
        return None  # اتسجل قبل كده
    debit = sum((_money(dr) for _, dr, _ in lines), Decimal("0"))
    credit = sum((_money(cr) for _, _, cr in lines), Decimal("0"))
    if debit != credit:
        raise ValueError(f"القيد مش متوازن: مدين {debit} دائن {credit}")
    journal = Journal.objects.get(company=company, code=journal_code)
    entry = JournalEntry.objects.create(company=company, journal=journal, reference=reference,
                                        memo=memo, created_by=user)
    for code, dr, cr in lines:
        if _money(dr) == 0 and _money(cr) == 0:
            continue
        JournalLine.objects.create(entry=entry, account=Account.objects.get(company=company, code=code),
                                   debit=_money(dr), credit=_money(cr))
    return entry


def post_sale(order, user=None):
    """بعد التسليم: مدين العملاء، دائن الإيراد + ضريبة المخرجات، ومدين تكلفة البضاعة ودائن المخزون."""
    company = order.company
    rate = current_values(company, "sales")["tax_rate"] / Decimal("100")
    net = _money(order.total)
    vat = _money(net * rate)
    cost = _money(sum((l.qty * l.product.cost for l in order.lines.select_related("product")), Decimal("0")))
    lines = [("1200", net + vat, 0), ("4000", 0, net), ("2200", 0, vat)]
    if cost:
        lines += [("5000", cost, 0), ("1300", 0, cost)]
    return _post(company, "SAL", order.number, f"فاتورة بيع {order.number}", lines, user)


def post_purchase(order, user=None):
    """بعد الاستلام: مدين المخزون + ضريبة المدخلات، ودائن الموردين."""
    company = order.company
    rate = current_values(company, "accounting")["default_tax"] / Decimal("100")
    net = _money(order.total)
    vat = _money(net * rate)
    lines = [("1300", net, 0), ("1400", vat, 0), ("2100", 0, net + vat)]
    return _post(company, "PUR", order.number, f"استلام {order.number}", lines, user)


def trial_balance(company):
    rows = []
    for acc in Account.objects.filter(company=company).order_by("code"):
        agg = JournalLine.objects.filter(account=acc, entry__company=company).aggregate(
            d=Sum("debit"), c=Sum("credit"))
        rows.append({"account": acc, "debit": agg["d"] or Decimal("0"), "credit": agg["c"] or Decimal("0")})
    total_d = sum((r["debit"] for r in rows), Decimal("0"))
    total_c = sum((r["credit"] for r in rows), Decimal("0"))
    return rows, total_d, total_c
