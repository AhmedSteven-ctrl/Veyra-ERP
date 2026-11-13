from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from core.settings_schema import current_values

from .chart import ROOT_CODES, account_for, load_default_chart, upgrade_legacy_accounts
from .models import Account, Journal, JournalEntry, JournalLine

JOURNALS = [("SAL", "يومية المبيعات"), ("PUR", "يومية المشتريات"), ("PAY", "يومية المدفوعات")]


def _money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_chart(company):
    """يتأكد إن الشركة عندها اليوميات ودليل الحسابات. أول مرة بيحمّل الدليل الافتراضي (ويرحّل الدليل القديم لو موجود)."""
    for code, name in JOURNALS:
        Journal.objects.get_or_create(company=company, code=code, defaults={"name": name})
    if not Account.objects.filter(company=company, code__in=ROOT_CODES).exists():
        load_default_chart(company)
        upgrade_legacy_accounts(company)


def _post(company, journal_code, reference, memo, lines, user=None):
    """lines = [(دور أو حساب، مدين، دائن)]. الدور (زي "receivable") بيتحوّل للحساب الافتراضي للشركة."""
    ensure_chart(company)
    if JournalEntry.objects.filter(company=company, reference=reference, journal__code=journal_code).exists():
        return None  # اتسجل قبل كده
    resolved = [(ref if isinstance(ref, Account) else account_for(company, ref), _money(dr), _money(cr))
                for ref, dr, cr in lines]
    debit = sum((dr for _, dr, _ in resolved), Decimal("0"))
    credit = sum((cr for _, _, cr in resolved), Decimal("0"))
    if debit != credit:
        raise ValueError(f"القيد مش متوازن: مدين {debit} دائن {credit}")
    for account, dr, cr in resolved:
        if dr == 0 and cr == 0:
            continue
        if account.company_id != company.id:
            raise ValueError(f"الحساب {account} مش تبع الشركة دي")
        if account.is_group:
            raise ValueError(f"الحساب {account} تجميعي ومينفعش يتسجّل عليه قيد")
        if not account.is_active:
            raise ValueError(f"الحساب {account} موقوف")
    journal = Journal.objects.get(company=company, code=journal_code)
    entry = JournalEntry.objects.create(company=company, journal=journal, reference=reference,
                                        memo=memo, created_by=user)
    for account, dr, cr in resolved:
        if dr == 0 and cr == 0:
            continue
        JournalLine.objects.create(entry=entry, account=account, debit=dr, credit=cr)
    return entry


def post_sale(order, user=None):
    """بعد التسليم: مدين العملاء، دائن الإيراد + ضريبة المخرجات، ومدين تكلفة البضاعة ودائن المخزون."""
    company = order.company
    rate = current_values(company, "sales")["tax_rate"] / Decimal("100")
    net = _money(order.total)
    vat = _money(net * rate)
    cost = _money(sum((l.qty * l.product.cost for l in order.lines.select_related("product")), Decimal("0")))
    lines = [("receivable", net + vat, 0), ("sales", 0, net), ("vat_output", 0, vat)]
    if cost:
        lines += [("cogs", cost, 0), ("inventory", 0, cost)]
    return _post(company, "SAL", order.number, f"فاتورة بيع {order.number}", lines, user)


def purchase_amounts(order):
    """(الصافي، الضريبة، الإجمالي) لأمر الشراء بنسبة ضريبة المشتريات الحالية."""
    rate = current_values(order.company, "accounting")["default_purchase_tax"] / Decimal("100")
    net = _money(order.total)
    vat = _money(net * rate)
    return net, vat, net + vat


def post_purchase(order, user=None, amounts=None):
    """بعد الاستلام: مدين المخزون + ضريبة المدخلات، ودائن الموردين. الأمر بإجمالي صفر مفيهوش قيد.
    amounts = (الصافي، الضريبة، الإجمالي) لو الاستلام حسبها قبل كده، عشان نفس الأرقام تتسجّل في القيد وفي الأمر."""
    net, vat, total = amounts or purchase_amounts(order)
    if total == 0:
        return None
    lines = [("inventory", net, 0), ("vat_input", vat, 0), ("payable", 0, total)]
    return _post(order.company, "PUR", order.number, f"استلام {order.number}", lines, user)


def post_supplier_payment(payment, user=None):
    """دفعة للمورد: مدين الموردين، ودائن الخزينة (نقدي) أو البنك (تحويل). لكل دفعة مرجع خاص بيها."""
    order = payment.order
    amount = _money(payment.amount)
    lines = [("payable", amount, 0), ("bank" if payment.method == "bank" else "cash", 0, amount)]
    return _post(order.company, "PAY", f"{order.number}-P{payment.pk}",
                 f"دفعة للمورد على الأمر {order.number}", lines, user)


def trial_balance(company, include_zero=False):
    """ميزان المراجعة: [{account, debit, credit}] للحسابات اللي عليها حركة (أو كلها لو include_zero)، والإجماليين."""
    sums = {row["account_id"]: row for row in JournalLine.objects.filter(entry__company=company)
            .values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))}
    rows = []
    for account in Account.objects.filter(company=company).order_by("code"):
        row = sums.get(account.pk)
        debit = (row["d"] if row else None) or Decimal("0")
        credit = (row["c"] if row else None) or Decimal("0")
        if include_zero or debit or credit:
            rows.append({"account": account, "debit": debit, "credit": credit})
    total_d = sum((r["debit"] for r in rows), Decimal("0"))
    total_c = sum((r["credit"] for r in rows), Decimal("0"))
    return rows, total_d, total_c
