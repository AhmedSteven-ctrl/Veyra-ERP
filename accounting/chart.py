"""منطق دليل الحسابات: تحميل الدليل الافتراضي، ترقية الحسابات القديمة، الهرم، الحسابات الافتراضية،
الأرصدة، الاستيراد والتصدير، وقواعد الحذف. مفيش هنا أي حاجة بتخص الشاشات."""
import csv
import io
import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .chart_data import CHART_ROWS
from .models import Account, AccountMapping, JournalLine

# الحساب الافتراضي لكل دور من الدليل الافتراضي (ممكن تغييره من شاشة «الحسابات الافتراضية»)
DEFAULT_ROLE_CODES = {
    "receivable": "141000", "payable": "211000", "inventory": "121000",
    "vat_input": "141400", "vat_output": "212200", "sales": "411000", "cogs": "511000",
    "cash": "151000", "bank": "151100",
}
ROOT_CODES = ("100000", "200000", "300000", "400000", "500000")

# الدليل القديم (4 أرقام): الكود -> (الاسم، الكود الجديد). بنستخدمه عشان نرحّل القيود القديمة للحسابات الجديدة.
LEGACY_CHART = {
    "1010": ("النقدية والبنك", "151000"), "1200": ("العملاء", "141000"), "1300": ("المخزون", "121000"),
    "1400": ("ضريبة مدخلات", "141400"), "2100": ("الموردون", "211000"), "2200": ("ضريبة مخرجات", "212200"),
    "4000": ("إيرادات المبيعات", "411000"), "5000": ("تكلفة البضاعة المباعة", "511000"),
}

_BROAD_BY_KIND = {
    "fixed_asset": "asset", "current_asset": "asset", "receivable": "asset", "bank_cash": "asset",
    "prepayment": "asset", "payable": "liability", "current_liability": "liability",
    "non_current_liability": "liability", "equity": "equity", "income": "income", "other_income": "income",
    "cost_of_revenue": "expense", "expense": "expense", "depreciation": "expense",
}
_BROAD_BY_DIGIT = {"1": "asset", "2": "liability", "3": "equity", "4": "income", "5": "expense"}


def broad_type(kind, code):
    """التصنيف العام (أصل/التزام/حقوق ملكية/إيراد/مصروف) من نوع الحساب، أو من أول رقم في الكود للحسابات التجميعية."""
    return _BROAD_BY_KIND.get(kind) or _BROAD_BY_DIGIT.get((code or "")[:1], "asset")


def default_nature(broad):
    return "debit" if broad in ("asset", "expense") else "credit"


def default_statement(broad):
    return "balance_sheet" if broad in ("asset", "liability", "equity") else "income_statement"


# ============================== الهرم ==============================
def suggest_parent(code, groups, five_digit_rule=True):
    """الحساب الرئيسي المقترح لكود. groups = {الكود: هل هو تجميعي؟} للحسابات الموجودة.
    القاعدة: أقرب حساب تجميعي بالتدرج (111110 ← 110000 ← 100000). وبقاعدة الخمس خانات (للدليل الافتراضي بس)
    الحساب XXXXY0 تابع لـ XXXX00 لو موجود (111110 ← 111100)، لأن الدليل الافتراضي مبني كده."""
    if five_digit_rule and len(code) == 6 and code[5] == "0" and code[4] != "0":
        candidate = code[:4] + "00"
        if candidate in groups:
            return candidate
    for k in range(1, len(code)):
        candidate = code[:len(code) - k] + "0" * k
        if candidate != code and groups.get(candidate):
            return candidate
    return None


def account_tree(company, accounts=None):
    """الحسابات بترتيب الشجرة: [(account, depth)]. الأب قبل أولاده، والإخوة بترتيب الكود."""
    accounts = list(accounts if accounts is not None
                    else Account.objects.filter(company=company).select_related("parent"))
    children = {}
    for acc in sorted(accounts, key=lambda a: a.code):
        children.setdefault(acc.parent_id, []).append(acc)
    known = {a.pk for a in accounts}
    out, seen = [], set()

    def walk(acc, depth):
        if acc.pk in seen:
            return
        seen.add(acc.pk)
        out.append((acc, depth))
        for child in children.get(acc.pk, []):
            walk(child, depth + 1)

    for acc in sorted(accounts, key=lambda a: a.code):
        if acc.parent_id is None or acc.parent_id not in known:
            walk(acc, 0)
    for acc in sorted(accounts, key=lambda a: a.code):  # أي حاجة اتبقت (دورة غريبة) بنعرضها برضه
        walk(acc, 0)
    return out


def descendant_ids(account):
    """كل الحسابات اللي تحت حساب (بأي عمق). بنستخدمها عشان نمنع دورة في الهرم."""
    children = {}
    for pk, parent_id in Account.objects.filter(company_id=account.company_id).values_list("id", "parent_id"):
        children.setdefault(parent_id, []).append(pk)
    found, stack = set(), [account.pk]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


# ============================== تحميل الدليل ==============================
@transaction.atomic
def load_default_chart(company):
    """ينشئ الحسابات الناقصة من الدليل الافتراضي. مبيعدّلش ولا يمسح أي حساب موجود. بيرجّع عدد الحسابات الجديدة."""
    existing = {a.code: a for a in Account.objects.filter(company=company)}
    created = []
    for code, name, kind, nature, statement, description, is_group in CHART_ROWS:
        if code in existing:
            continue
        account = Account.objects.create(company=company, code=code, name=name, type=broad_type(kind, code),
                                         kind=kind, nature=nature, statement=statement,
                                         description=description, is_group=is_group)
        existing[code] = account
        created.append(account)
    default_groups = {row[0]: row[6] for row in CHART_ROWS}
    with_parent = []
    for account in created:
        parent_code = suggest_parent(account.code, default_groups)
        if parent_code and parent_code in existing:
            account.parent = existing[parent_code]
            with_parent.append(account)
    if with_parent:
        Account.objects.bulk_update(with_parent, ["parent"])
    return len(created)


@transaction.atomic
def upgrade_legacy_accounts(company):
    """الدليل القديم (1010، 1200...): بينقل قيوده للحساب الجديد المقابل ويمسح الحساب القديم.
    بيتأكد إن الاسم هو اسم الحساب القديم الأصلي عشان ما يلمسش حساب المستخدم بنفسه عمله بنفس الكود."""
    moved = 0
    for old_code, (old_name, new_code) in LEGACY_CHART.items():
        legacy = Account.objects.filter(company=company, code=old_code, name=old_name).first()
        target = Account.objects.filter(company=company, code=new_code).first()
        if legacy is None or target is None or legacy.pk == target.pk:
            continue
        if legacy.children.exists() or legacy.mappings.exists():
            continue
        moved += JournalLine.objects.filter(account=legacy).update(account=target)
        legacy.delete()
    return moved


# ============================== الحسابات الافتراضية ==============================
def role_label(role):
    return dict(AccountMapping.ROLES)[role]


def account_for(company, role):
    """الحساب المستخدم لدور معيّن: اللي اتحدد في «الحسابات الافتراضية»، وإلا حساب الدليل الافتراضي."""
    mapping = AccountMapping.objects.filter(company=company, role=role).select_related("account").first()
    account = mapping.account if mapping else Account.objects.filter(
        company=company, code=DEFAULT_ROLE_CODES[role]).first()
    if account is None:
        raise ValueError(f"حساب «{role_label(role)}» مش موجود. حدده من «الحسابات الافتراضية».")
    return account


def role_usage(account):
    """أسماء الأدوار اللي الحساب ده مستخدم فيها كحساب افتراضي (بالتحديد أو بالكود الافتراضي)."""
    mapped = {m.role: m.account_id for m in AccountMapping.objects.filter(company_id=account.company_id)}
    labels = []
    for role, code in DEFAULT_ROLE_CODES.items():
        if role in mapped:
            used = mapped[role] == account.pk
        else:
            used = account.code == code
        if used:
            labels.append(role_label(role))
    return labels


# ============================== الأرصدة ==============================
def account_balances(company):
    """صافي (مدين - دائن) لكل حساب شامل الحسابات اللي تحته: {account_id: Decimal}."""
    own = {}
    for row in (JournalLine.objects.filter(entry__company=company).values("account_id")
                .annotate(d=Sum("debit"), c=Sum("credit"))):
        own[row["account_id"]] = (row["d"] or Decimal("0")) - (row["c"] or Decimal("0"))
    parent_of = dict(Account.objects.filter(company=company).values_list("id", "parent_id"))
    total = {pk: Decimal("0") for pk in parent_of}
    for pk, amount in own.items():
        if pk not in total:
            continue
        total[pk] += amount
        seen, parent = {pk}, parent_of.get(pk)
        while parent and parent not in seen and parent in total:
            total[parent] += amount
            seen.add(parent)
            parent = parent_of.get(parent)
    return total


def balance_for_display(account, net):
    """الرصيد بعلامة طبيعة الحساب: حساب مدين بيظهر مدين - دائن، وحساب دائن بيظهر دائن - مدين."""
    return net if account.nature == "debit" else -net


# ============================== الحذف ==============================
def delete_blockers(account):
    """أسباب منع مسح الحساب (قايمة فاضية = ينفع يتمسح)."""
    reasons = []
    if account.lines.exists():
        reasons.append("عليه قيود محاسبية (وقّفه بدل ما تمسحه)")
    if account.children.exists():
        reasons.append("تحته حسابات فرعية")
    used = role_usage(account)
    if used:
        reasons.append("مستخدم كحساب افتراضي: " + "، ".join(used))
    return reasons


# ============================== استيراد وتصدير CSV ==============================
CSV_COLUMNS = ["code", "name", "kind", "nature", "statement", "parent_code", "is_group", "is_active", "description"]
MAX_IMPORT_ROWS = 5000
_TRUE = {"1", "true", "yes", "y", "نعم", "صح"}
_FALSE = {"0", "false", "no", "n", "لا", "خطأ"}


def export_csv(company):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for account, _depth in account_tree(company):
        writer.writerow([account.code, account.name, account.kind, account.nature, account.statement,
                         account.parent.code if account.parent_id else "", 1 if account.is_group else 0,
                         1 if account.is_active else 0, account.description])
    return buffer.getvalue()


def _alias(keys, labeled):
    out = {key: key for key in keys}
    out.update({label: key for key, label in labeled})
    return out


_KIND_ALIAS = _alias([k for k, _ in Account.KINDS], Account.KINDS)
_NATURE_ALIAS = _alias([k for k, _ in Account.NATURES], Account.NATURES)
_STATEMENT_ALIAS = _alias([k for k, _ in Account.STATEMENTS], Account.STATEMENTS)


def _flag(value, default):
    text = (value or "").strip().lower()
    if text == "":
        return default
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"قيمة صح/خطأ غير مفهومة: {value}")


def import_csv(company, text):
    """يستورد حسابات من CSV (نفس أعمدة التصدير؛ code وname إجباريين). الحساب الموجود بنفس الكود بيتعدّل والجديد بيتضاف.
    مبيمسحش حاجة. لو أي صف فيه خطأ مفيش حاجة بتتحفظ. بيرجّع (عدد الجديد، عدد المعدّل، الأخطاء)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    columns = [(c or "").strip() for c in (reader.fieldnames or [])]
    if "code" not in columns or "name" not in columns:
        return 0, 0, ["الملف لازم يبدأ بصف عناوين فيه العمودين code وname على الأقل (الأفضل تصدّر الدليل وتعدّل عليه)."]
    existing = {a.code: a for a in Account.objects.filter(company=company).select_related("parent")}
    errors, parsed, seen = [], [], set()
    for number, raw in enumerate(reader, start=2):
        if number - 1 > MAX_IMPORT_ROWS:
            errors.append(f"الملف أكبر من {MAX_IMPORT_ROWS} صف.")
            break
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        code, name = row.get("code", ""), row.get("name", "")
        problems = []
        if not re.fullmatch(r"\d{3,10}", code):
            problems.append("الكود لازم أرقام (3 إلى 10 خانات)")
        elif code in seen:
            problems.append("الكود مكرر في الملف")
        seen.add(code)
        if not name or len(name) > 150:
            problems.append("الاسم فاضي أو أطول من 150 حرف")
        old = existing.get(code)
        kind = _KIND_ALIAS.get(row.get("kind", ""), None) if row.get("kind") else (old.kind if old else "current_asset")
        if kind is None:
            problems.append(f"نوع الحساب غير معروف: {row['kind']}")
        broad = broad_type(kind, code) if kind else "asset"
        nature = (_NATURE_ALIAS.get(row["nature"]) if row.get("nature")
                  else (old.nature if old else default_nature(broad)))
        if nature is None:
            problems.append(f"الطبيعة غير معروفة: {row['nature']}")
        statement = (_STATEMENT_ALIAS.get(row["statement"]) if row.get("statement")
                     else (old.statement if old else default_statement(broad)))
        if statement is None:
            problems.append(f"القائمة المالية غير معروفة: {row['statement']}")
        try:
            is_group = _flag(row.get("is_group"), old.is_group if old else False)
            is_active = _flag(row.get("is_active"), old.is_active if old else True)
        except ValueError as exc:
            problems.append(str(exc))
            is_group, is_active = False, True
        if old and is_group and not old.is_group and old.lines.exists():
            problems.append("الحساب عليه قيود فمينفعش يتحول لتجميعي")
        if old and ((is_group and not old.is_group) or (not is_active and old.is_active)) and role_usage(old):
            problems.append("الحساب مستخدم كحساب افتراضي فمينفعش يتوقف أو يتحول لتجميعي")
        if problems:
            errors.append(f"سطر {number} ({code or '؟'}): " + "، ".join(problems))
            continue
        parsed.append({"code": code, "name": name, "kind": kind, "nature": nature, "statement": statement,
                       "is_group": is_group, "is_active": is_active, "description": row.get("description", "")[:255],
                       "parent_code": row.get("parent_code", ""), "line": number})
    # الأب لازم يكون موجود (في الملف أو في الدليل) ومفيش دورة
    parent_codes = {c: (a.parent.code if a.parent_id else None) for c, a in existing.items()}
    known = set(existing) | {p["code"] for p in parsed}
    for item in parsed:
        parent_code = item["parent_code"]
        if not parent_code:
            continue
        if parent_code == item["code"] or parent_code not in known:
            errors.append(f"سطر {item['line']} ({item['code']}): الحساب الرئيسي {parent_code} غير موجود أو هو نفس الحساب")
        else:
            parent_codes[item["code"]] = parent_code
    for code in list(parent_codes):
        walked, current = set(), code
        while current:
            if current in walked:
                errors.append(f"الحساب {code} داخل في دورة في الهرم")
                break
            walked.add(current)
            current = parent_codes.get(current)
    if errors:
        return 0, 0, errors
    created = updated = 0
    with transaction.atomic():
        objects = dict(existing)
        for item in parsed:
            fields = {"name": item["name"], "kind": item["kind"], "type": broad_type(item["kind"], item["code"]),
                      "nature": item["nature"], "statement": item["statement"], "is_group": item["is_group"],
                      "is_active": item["is_active"], "description": item["description"]}
            if item["code"] in objects:
                account = objects[item["code"]]
                for key, value in fields.items():
                    setattr(account, key, value)
                account.save()
                updated += 1
            else:
                objects[item["code"]] = Account.objects.create(company=company, code=item["code"], **fields)
                created += 1
        groups = {c: a.is_group for c, a in objects.items()}
        for item in parsed:
            account = objects[item["code"]]
            if item["parent_code"]:
                parent = objects[item["parent_code"]]
            elif account.parent_id is None:
                suggested = suggest_parent(account.code, groups, five_digit_rule=False)
                parent = objects[suggested] if suggested else None
            else:
                continue
            if parent != account.parent:
                account.parent = parent
                account.save(update_fields=["parent"])
    return created, updated, []
