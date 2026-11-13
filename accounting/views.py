from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.decorators import module_required
from core.icons import svg_for
from core.views import MENUS, _is_manager, _list_page, _render_form

from .chart import (account_balances, account_for, account_tree, balance_for_display, delete_blockers, export_csv,
                    import_csv, load_default_chart, role_usage, upgrade_legacy_accounts)
from .forms import AccountForm, AccountImportForm, AccountRolesForm
from .models import Account, AccountMapping, JournalEntry, JournalLine
from .services import ensure_chart, trial_balance

_PILL = {"asset": "ok-p", "liability": "warn-p", "equity": "mute-p", "income": "ok-p", "expense": "low-p"}


def _require_manager(request):
    """تعديل دليل الحسابات للمدير بس. أي مستخدم عنده صلاحية المحاسبة يقدر يشوفه."""
    if not _is_manager(request.user):
        raise PermissionDenied


# ============================== دليل الحسابات ==============================
@module_required("accounting")
def account_list(request):
    company = request.user.company
    ensure_chart(company)  # أول مرة للشركة: بيتحمّل الدليل الافتراضي
    balances = account_balances(company)
    rows = []
    for account, depth in account_tree(company):
        net = balances.get(account.pk, Decimal("0"))
        name = "\u00a0\u00a0\u00a0\u00a0" * depth + account.name + ("" if account.is_active else "  · موقوف")
        rows.append({
            "id": account.pk, "s": account.type, "detail": "account_detail", "group": account.is_group,
            "pill": _PILL.get(account.type, ""),
            "cells": [account.code, name, account.get_kind_display(), account.get_nature_display(),
                      account.get_statement_display(), balance_for_display(account, net) if net else "—"],
        })
    manager = _is_manager(request.user)
    creates = ([("حساب جديد", "account_create"), ("استيراد CSV", "account_import")] if manager else []) + [
        ("تصدير CSV", "account_export")]
    post_actions = [("تحميل الدليل الافتراضي", "account_load_default",
                     "هيضيف أي حسابات ناقصة من الدليل الافتراضي (من غير ما يعدّل أو يمسح حاجة). متأكد؟")] if manager else []
    return _list_page(request, code="accounting", title="دليل الحسابات", rows=rows,
                      columns=["الكود", "الحساب", "النوع", "الطبيعة", "القائمة المالية", "الرصيد"],
                      statuses=list(Account.TYPES), creates=creates, post_actions=post_actions)


@module_required("accounting")
def account_detail(request, pk):
    company = request.user.company
    account = get_object_or_404(Account.objects.select_related("parent"), pk=pk, company=company)
    own = JournalLine.objects.filter(account=account).aggregate(d=Sum("debit"), c=Sum("credit"))
    debit, credit = own["d"] or Decimal("0"), own["c"] or Decimal("0")
    net = account_balances(company).get(account.pk, Decimal("0"))
    fields = [("الكود", account.code), ("الاسم", account.name), ("التصنيف", account.get_type_display()),
              ("نوع الحساب", account.get_kind_display()),
              ("الحساب الرئيسي", str(account.parent) if account.parent_id else "—"),
              ("الطبيعة", account.get_nature_display()), ("القائمة المالية", account.get_statement_display()),
              ("الحالة", "نشط" if account.is_active else "موقوف"),
              ("يقبل قيود", "لا (تجميعي)" if account.is_group else "نعم"),
              ("إجمالي المدين", debit), ("إجمالي الدائن", credit),
              ("الرصيد" + (" (شامل الحسابات الفرعية)" if account.is_group else ""),
               balance_for_display(account, net))]
    if account.description:
        fields.append(("الوصف", account.description))
    usage = role_usage(account)
    if usage:
        fields.append(("حساب افتراضي لـ", "، ".join(usage)))
    movements = (JournalLine.objects.filter(account=account).select_related("entry__journal")
                 .order_by("-entry__created_at", "-id")[:200])
    rows = [(l.entry.created_at.strftime("%Y-%m-%d"), l.entry.reference, l.entry.journal.name, l.entry.memo,
             l.debit, l.credit) for l in movements]
    tables = [{"title": "آخر الحركات", "cols": ["التاريخ", "المرجع", "اليومية", "البيان", "مدين", "دائن"],
               "rows": rows}] if rows else []
    manager = _is_manager(request.user)
    actions = []
    if manager:
        actions.append({"url": "account_toggle", "post": True,
                        "label": "إيقاف الحساب" if account.is_active else "تفعيل الحساب"})
        actions.append({"url": "account_delete", "post": True, "label": "حذف", "ghost": True,
                        "confirm": "هتمسح الحساب ده نهائيًا. متأكد؟"})
    return render(request, "detail.html", {
        "code": "accounting", "title": account.name, "obj": account, "fields": fields,
        "edit_url": "account_edit" if manager else None, "actions": actions, "tables": tables,
        "steps": [], "lines": None, "line_cols": [], "extra": [],
        "menus": MENUS.get("accounting", []), "icon": svg_for("accounting"),
    })


@module_required("accounting")
def account_create(request):
    _require_manager(request)
    company = request.user.company
    form = AccountForm(request.POST or None, instance=Account(company=company), company=company)
    if request.method == "POST" and form.is_valid():
        account = form.save()
        messages.success(request, f"تم إضافة الحساب {account}")
        return redirect("account_detail", pk=account.pk)
    return _render_form(request, code="accounting", title="حساب جديد", form=form, back_url="account_list")


@module_required("accounting")
def account_edit(request, pk):
    _require_manager(request)
    company = request.user.company
    account = get_object_or_404(Account, pk=pk, company=company)
    form = AccountForm(request.POST or None, instance=account, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديلات")
        return redirect("account_detail", pk=account.pk)
    return _render_form(request, code="accounting", title=f"تعديل {account}", form=form, back_url="account_list")


@module_required("accounting")
@require_POST
def account_toggle(request, pk):
    _require_manager(request)
    account = get_object_or_404(Account, pk=pk, company=request.user.company)
    if account.is_active:
        usage = role_usage(account)
        if usage:
            messages.error(request, "الحساب مستخدم كحساب افتراضي (" + "، ".join(usage)
                           + "). غيّره من «الحسابات الافتراضية» الأول")
            return redirect("account_detail", pk=pk)
    account.is_active = not account.is_active
    account.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "تم تفعيل الحساب" if account.is_active else "تم إيقاف الحساب")
    return redirect("account_detail", pk=pk)


@module_required("accounting")
@require_POST
def account_delete(request, pk):
    _require_manager(request)
    account = get_object_or_404(Account, pk=pk, company=request.user.company)
    reasons = delete_blockers(account)
    if reasons:
        messages.error(request, "مينفعش تمسح الحساب: " + " - ".join(reasons))
        return redirect("account_detail", pk=pk)
    label = str(account)
    account.delete()
    messages.success(request, f"تم مسح الحساب {label}")
    return redirect("account_list")


@module_required("accounting")
@require_POST
def account_load_default(request):
    _require_manager(request)
    company = request.user.company
    created = load_default_chart(company)
    moved = upgrade_legacy_accounts(company)
    ensure_chart(company)
    messages.success(request, f"تمت إضافة {created} حساب جديد من الدليل الافتراضي"
                     + (f" ونقل {moved} حركة من الحسابات القديمة" if moved else ""))
    return redirect("account_list")


# ============================== الحسابات الافتراضية ==============================
@module_required("accounting")
def account_roles(request):
    _require_manager(request)
    company = request.user.company
    ensure_chart(company)
    current = {}
    for role, _label in AccountMapping.ROLES:
        try:
            current[role] = account_for(company, role)
        except ValueError:
            pass
    form = AccountRolesForm(request.POST or None, company=company, current=current)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ الحسابات الافتراضية")
        return redirect("account_roles")
    return _render_form(request, code="accounting", title="الحسابات الافتراضية", form=form, back_url="account_list")


# ============================== استيراد وتصدير ==============================
@module_required("accounting")
def account_export(request):
    ensure_chart(request.user.company)
    response = HttpResponse("\ufeff" + export_csv(request.user.company), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="chart_of_accounts.csv"'
    return response


@module_required("accounting")
def account_import(request):
    _require_manager(request)
    company = request.user.company
    form = AccountImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        created, updated, errors = import_csv(company, form.cleaned_data["file"])
        if errors:
            for error in errors[:15]:
                form.add_error(None, error)
            if len(errors) > 15:
                form.add_error(None, f"... و{len(errors) - 15} خطأ تاني")
        else:
            messages.success(request, f"تم الاستيراد: {created} حساب جديد و{updated} معدّل")
            return redirect("account_list")
    return _render_form(request, code="accounting", title="استيراد دليل الحسابات", form=form, back_url="account_list")


# ============================== اليوميات والميزان ==============================
@module_required("accounting")
def journal_list(request):
    entries = JournalEntry.objects.filter(company=request.user.company).select_related("journal")
    rows = [{"id": e.id, "s": "posted", "detail": None,
             "cells": [e.reference, e.journal.name, e.memo, e.created_at.strftime("%Y-%m-%d")]} for e in entries]
    return _list_page(request, code="accounting", title="القيود اليومية", rows=rows,
                      columns=["المرجع", "اليومية", "البيان", "التاريخ"], statuses=[("posted", "مرحّل")], create=False)


@module_required("accounting")
def trial_balance_view(request):
    show_all = request.GET.get("all") == "1"
    rows, total_d, total_c = trial_balance(request.user.company, include_zero=show_all)
    return render(request, "trial_balance.html", {
        "rows": rows, "total_d": total_d, "total_c": total_c, "balanced": total_d == total_c,
        "show_all": show_all, "menus": MENUS.get("accounting", []), "icon": "📊", "title": "ميزان المراجعة",
    })
