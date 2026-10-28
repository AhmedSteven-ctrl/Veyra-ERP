from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory.forms import ProductForm
from inventory.models import Product, Warehouse
from inventory.services import StockError
from purchasing.forms import PurchaseLineFormSet, PurchaseOrderForm, PurchasePaymentForm
from purchasing.models import PAYMENT_LABELS, PurchaseOrder, PurchasePayment, payment_state
from purchasing.services import cancel_order as cancel_purchase
from purchasing.services import confirm_order as confirm_purchase
from purchasing.services import pay_order, receive_order
from sales.forms import SalesLineFormSet, SalesOrderForm
from sales.models import SalesOrder
from sales.services import confirm_order as confirm_sale
from sales.services import deliver

from .decorators import module_required
from .forms import PartnerForm
from .icons import svg_for
from .settings_schema import SCHEMA, build_form, current_values, grouped, save_values
from .models import CompanyModule, Module, Partner

# الشاشات المنفذة حالياً (كود المديول -> اسم الـ URL)
IMPLEMENTED = {"inventory": "product_list", "sales": "sales_orders", "purchasing": "purchase_orders", "contacts": "partner_list", "settings": "settings_index", "accounting": "journal_list"}
ICONS = {"inventory": "📦", "sales": "🧾", "purchasing": "🛒", "accounting": "📊", "contacts": "👤", "crm": "🤝",
         "employees": "👥", "manufacturing": "🏭", "quality": "✅", "maintenance": "🔧", "settings": "⚙"}
PALETTE = [("#3D63F5", "#7A4DFF"), ("#0FAF7B", "#6EE7B7"), ("#F2A20C", "#FCD34D"), ("#E5484D", "#FCA5A5"),
           ("#0EA5E9", "#7DD3FC"), ("#8B5CF6", "#C4B5FD"), ("#64748B", "#A3B1C6"), ("#F97316", "#FDBA74")]
MENUS = {
    "inventory": [("المنتجات والأرصدة", "product_list")],
    "sales": [("أوامر البيع", "sales_orders")],
    "purchasing": [("أوامر الشراء", "purchase_orders"), ("مدفوعات الموردين", "purchase_payments")],
    "contacts": [("جهات الاتصال", "partner_list")],
    "accounting": [("القيود اليومية", "journal_list"), ("ميزان المراجعة", "trial_balance")],
}
SALES_ACTIONS = {"draft": ("sales_confirm", "تأكيد الأمر"), "confirmed": ("sales_deliver", "تسليم وخصم من المخزن")}
PURCHASE_ACTIONS = {"draft": ("purchase_confirm", "تأكيد الأمر"), "confirmed": ("purchase_receive", "استلام وإدخال للمخزن")}
CREATE_URLS = {"inventory": "product_create", "sales": "sales_create", "purchasing": "purchase_create",
               "contacts": "partner_create"}


def _warehouse(company):
    """أول مخزن للشركة. لو ملهاش مخزن بنعمل "المخزن الرئيسي" تلقائي عشان التسليم والاستلام ما يقفوش."""
    warehouse = Warehouse.objects.filter(company=company).order_by("id").first()
    if warehouse is None:
        warehouse, _ = Warehouse.objects.get_or_create(company=company, code="MAIN",
                                                       defaults={"name": "المخزن الرئيسي"})
    return warehouse


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    user = request.user
    groups = []
    if user.company_id:
        visible = {m.code: m for m in Module.objects.filter(code__in=user.accessible_codes()).select_related("parent")}
        children = {}
        for m in visible.values():
            if m.parent_id and m.parent.code in visible:
                children.setdefault(m.parent.code, []).append(m)
        for i, m in enumerate(sorted((m for m in visible.values() if not (m.parent_id and m.parent.code in visible)),
                                     key=lambda x: (x.sort, x.name))):
            c1, c2 = PALETTE[i % len(PALETTE)]
            groups.append({"module": m, "icon": svg_for(m.code), "c1": c1, "c2": c2,
                           "url": IMPLEMENTED.get(m.code), "children": len(children.get(m.code, []))})
    return render(request, "home.html", {"groups": groups})


def _steps(statuses, current):
    keys = [k for k, _ in statuses]
    idx = keys.index(current) if current in keys else -1
    return [{"label": l, "state": "done" if i < idx else ("cur" if i == idx else "")}
            for i, (k, l) in enumerate(statuses)]


@module_required("inventory")
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.user.company)
    stock_now = product.stock_moves.aggregate(t=Sum("qty"))["t"] or Decimal("0")
    moves = product.stock_moves.select_related("warehouse")[:20]
    fields = [("الكود", product.code), ("الاسم", product.name), ("الباركود", product.barcode or "—"),
              ("الوحدة", product.unit), ("سعر البيع", product.sale_price), ("تكلفة الوحدة", product.cost),
              ("حد إعادة الطلب", product.min_qty), ("الرصيد الحالي", stock_now)]
    return render(request, "detail.html", {
        "code": "inventory", "title": product.name, "obj": product, "fields": fields, "edit_url": "product_edit",
        "steps": [], "lines": [(m.created_at.strftime("%Y-%m-%d %H:%M"), m.warehouse.name, m.get_kind_display(), m.qty, m.reference) for m in moves],
        "line_cols": ["التاريخ", "المخزن", "النوع", "الكمية", "المرجع"], "extra": [],
        "menus": MENUS.get("inventory", []), "icon": svg_for("inventory"),
    })


@module_required("sales")
def sales_detail(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, company=request.user.company)
    fields = [("الرقم", order.number), ("العميل", order.customer.name), ("الإجمالي", order.total)]
    lines = [(l.product.name, l.qty, l.price, l.subtotal) for l in order.lines.select_related("product")]
    return render(request, "detail.html", {
        "code": "sales", "title": order.number, "obj": order, "fields": fields, "edit_url": "sales_edit",
        "steps": _steps(SalesOrder.STATUS, order.status), "lines": lines,
        "line_cols": ["الصنف", "الكمية", "السعر", "الإجمالي"], "extra": [],
        "menus": MENUS.get("sales", []), "icon": svg_for("sales"),
    })


def _purchase_actions(order, user):
    """الأزرار المتاحة على أمر الشراء حسب حالته وصلاحيات المستخدم."""
    actions = []
    if order.status == "draft":
        actions.append({"url": "purchase_confirm", "label": "تأكيد الأمر", "post": True})
    if order.status == "confirmed":
        actions.append({"url": "purchase_receive", "label": "استلام وإدخال للمخزن", "post": True})
    if order.status in ("draft", "confirmed"):
        actions.append({"url": "purchase_cancel", "label": "إلغاء الأمر", "post": True,
                        "confirm": "هتلغي الأمر ده. متأكد؟"})
    if order.status == "received" and order.balance > 0 and user.can_access("accounting"):
        actions.append({"url": "purchase_pay", "label": "تسجيل دفعة", "post": False})
    return actions


@module_required("purchasing")
def purchase_detail(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    fields = [("الرقم", order.number), ("المورد", order.supplier.name), ("الإجمالي", order.total)]
    if order.status == "cancelled":
        fields.append(("الحالة", "ملغي"))
    if order.expected_date:
        fields.append(("تاريخ الاستلام المتوقع", order.expected_date))
    if order.status == "received":
        paid = order.paid
        fields += [("المستحق للمورد", order.billed_total), ("المدفوع", paid),
                   ("المتبقي", order.billed_total - paid),
                   ("حالة الدفع", PAYMENT_LABELS[payment_state(order.billed_total, paid)])]
    if order.notes:
        fields.append(("ملاحظات", order.notes))
    lines = [(l.product.name, l.qty, l.cost, l.subtotal) for l in order.lines.select_related("product")]
    method_labels = dict(PurchasePayment.METHODS)
    pay_rows = [(p.created_at.strftime("%Y-%m-%d"), p.amount, method_labels.get(p.method, p.method), p.note or "—")
                for p in order.payments.all()]
    tables = [{"title": "الدفعات", "cols": ["التاريخ", "المبلغ", "الطريقة", "ملاحظة"], "rows": pay_rows}] if pay_rows else []
    steps = [] if order.status == "cancelled" else _steps([x for x in PurchaseOrder.STATUS if x[0] != "cancelled"], order.status)
    return render(request, "detail.html", {
        "code": "purchasing", "title": order.number, "obj": order, "fields": fields,
        "edit_url": "purchase_edit" if order.status in ("draft", "confirmed") else None,
        "actions": _purchase_actions(order, request.user), "tables": tables,
        "steps": steps, "lines": lines,
        "line_cols": ["الصنف", "الكمية", "التكلفة", "الإجمالي"], "extra": [],
        "menus": MENUS.get("purchasing", []), "icon": svg_for("purchasing"),
    })


def _list_page(request, *, code, title, columns, rows, statuses, create=True):
    create_url = CREATE_URLS.get(code) if create else None
    f = request.GET.get("f", "")
    q = request.GET.get("q", "").strip()
    labels = dict(statuses)
    for r in rows:
        r["label"] = labels.get(r["s"], r["s"])
    stats = [{"key": "", "label": "الكل", "count": len(rows), "active": f == ""}]
    stats += [{"key": k, "label": l, "count": sum(1 for r in rows if r["s"] == k), "active": f == k}
              for k, l in statuses]
    needle = q.lower()

    def haystack(r):
        return (" ".join(str(c) for c in r["cells"]) + " " + r.get("search", "")).lower()

    shown = [r for r in rows if (not f or r["s"] == f) and (not needle or needle in haystack(r))]
    return render(request, "list.html", {
        "code": code, "title": title, "columns": columns, "stats": stats, "rows": shown, "create_url": create_url,
        "q": q, "statuses": dict(statuses), "menus": MENUS.get(code, []),
        "icon": svg_for(code),
    })


@module_required("inventory")
def product_list(request):
    products = (Product.objects.filter(company=request.user.company)
                .annotate(stock=Coalesce(Sum("stock_moves__qty"), Decimal("0"))))
    rows = [{"id": p.id, "s": "low" if p.stock < p.min_qty else "ok", "detail": "product_detail",
             "cells": [p.code, p.name, p.barcode or "—", p.sale_price, p.stock], "search": p.barcode}
            for p in products]
    return _list_page(request, code="inventory", title="المخزون", rows=rows,
                      columns=["الكود", "الصنف", "الباركود", "سعر البيع", "الرصيد"],
                      statuses=[("ok", "متوفر"), ("low", "تحت حد الطلب")])


@module_required("sales")
def sales_orders(request):
    orders = SalesOrder.objects.filter(company=request.user.company).select_related("customer")
    rows = [{"id": o.id, "s": o.status, "detail": "sales_detail", "cells": [o.number, o.customer.name, o.total],
             "action": SALES_ACTIONS.get(o.status)}
            for o in orders]
    return _list_page(request, code="sales", title="المبيعات", rows=rows,
                      columns=["الرقم", "العميل", "الإجمالي"],
                      statuses=[("draft", "مسودة"), ("confirmed", "مؤكد"), ("delivered", "تم التسليم")])


@module_required("sales")
@require_POST
def sales_deliver(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, company=request.user.company)
    try:
        deliver(order, _warehouse(request.user.company), user=request.user)
        messages.success(request, f"تم تسليم الأمر {order.number} وخصم الكميات من المخزن")
    except (StockError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales_orders")


@module_required("sales")
@require_POST
def sales_confirm(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, company=request.user.company)
    try:
        confirm_sale(order)
        messages.success(request, f"تم تأكيد الأمر {order.number}")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("sales_orders")


@module_required("purchasing")
def purchase_orders(request):
    orders = (PurchaseOrder.objects.filter(company=request.user.company).select_related("supplier")
              .annotate(paid_sum=Coalesce(Sum("payments__amount"), Decimal("0"))))
    rows = [{"id": o.id, "s": o.status, "detail": "purchase_detail",
             "cells": [o.number, o.supplier.name, o.total,
                       PAYMENT_LABELS[payment_state(o.billed_total, o.paid_sum)] if o.status == "received" else "—"],
             "action": PURCHASE_ACTIONS.get(o.status)}
            for o in orders]
    return _list_page(request, code="purchasing", title="الشراء", rows=rows,
                      columns=["الرقم", "المورد", "الإجمالي", "الدفع"],
                      statuses=[("draft", "مسودة"), ("confirmed", "بانتظار الاستلام"), ("received", "مستلم"),
                                ("cancelled", "ملغي")])


@module_required("purchasing")
def purchase_payments(request):
    payments = (PurchasePayment.objects.filter(order__company=request.user.company)
                .select_related("order__supplier"))
    method_labels = dict(PurchasePayment.METHODS)
    rows = [{"id": p.order_id, "s": p.method, "detail": "purchase_detail",
             "cells": [p.order.number, p.order.supplier.name, p.amount, method_labels.get(p.method, p.method),
                       p.created_at.strftime("%Y-%m-%d")]}
            for p in payments]
    return _list_page(request, code="purchasing", title="مدفوعات الموردين", rows=rows,
                      columns=["الأمر", "المورد", "المبلغ", "الطريقة", "التاريخ"],
                      statuses=list(PurchasePayment.METHODS), create=False)


@module_required("purchasing")
@require_POST
def purchase_receive(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    try:
        receive_order(order, _warehouse(request.user.company), user=request.user)
        messages.success(request, f"تم استلام الأمر {order.number} وإضافته للمخزن")
    except (StockError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("purchase_orders")


@module_required("purchasing")
@require_POST
def purchase_confirm(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    try:
        confirm_purchase(order)
        messages.success(request, f"تم تأكيد الأمر {order.number}")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchase_orders")


@module_required("purchasing")
@require_POST
def purchase_cancel(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    try:
        cancel_purchase(order)
        messages.success(request, f"تم إلغاء الأمر {order.number}")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchase_detail", pk=pk)


@module_required("purchasing")
def purchase_pay(request, pk):
    """تسجيل دفعة للمورد. بيعمل قيد محاسبي، فلازم المستخدم يكون له صلاحية المحاسبة كمان."""
    if not request.user.can_access("accounting"):
        raise PermissionDenied
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    if order.status != "received" or order.balance <= 0:
        messages.error(request, "مفيش مبلغ مستحق للمورد على الأمر ده")
        return redirect("purchase_detail", pk=pk)
    form = PurchasePaymentForm(request.POST or None, order=order)
    if request.method == "POST" and form.is_valid():
        try:
            payment = pay_order(order, form.cleaned_data["amount"], method=form.cleaned_data["method"],
                                note=form.cleaned_data["note"], user=request.user)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"تم تسجيل دفعة {payment.amount} للأمر {order.number}")
            return redirect("purchase_detail", pk=pk)
    return _render_form(request, code="purchasing", title=f"دفعة للأمر {order.number}", form=form,
                        back_url="purchase_orders")


# ================= الإنشاء والتعديل من الشاشة =================
DEFAULT_PREFIX = {"sales": "SO", "purchasing": "PO"}


def _next_number(model, company, module_code):
    """رقم الأمر الجاي بالبادئة اللي في إعدادات المديول (sales.prefix / purchasing.prefix)."""
    prefix = (current_values(company, module_code).get("prefix") or "").strip() or DEFAULT_PREFIX[module_code]
    n = model.objects.filter(company=company).count() + 1
    while model.objects.filter(company=company, number=f"{prefix}-{n:04d}").exists():
        n += 1
    return f"{prefix}-{n:04d}"


def _save_with_number(order, module_code):
    """يحفظ الأمر برقم جديد. لو مستخدمين اتنين خدوا نفس الرقم في نفس اللحظة نجرّب رقم تاني."""
    for _ in range(5):
        order.number = _next_number(type(order), order.company, module_code)
        try:
            with transaction.atomic():
                order.save()
            return
        except IntegrityError:
            continue
    raise IntegrityError("تعذّر توليد رقم فريد للأمر، جرّب تاني")


def _render_form(request, *, code, title, form, formset=None, back_url=None):
    return render(request, "form.html", {
        "code": code, "title": title, "form": form, "formset": formset,
        "back_url": back_url, "menus": MENUS.get(code, []), "icon": svg_for(code),
    })


@module_required("contacts")
def partner_list(request):
    partners = Partner.objects.filter(company=request.user.company)
    rows = [{"id": p.id, "s": p.kind, "detail": None, "cells": [p.name, p.phone, p.city]} for p in partners]
    return _list_page(request, code="contacts", title="جهات الاتصال", rows=rows,
                      columns=["الاسم", "الهاتف", "المدينة"],
                      statuses=[("customer", "عميل"), ("supplier", "مورد"), ("both", "عميل ومورد")])


@module_required("contacts")
def partner_create(request):
    company = request.user.company
    form = PartnerForm(request.POST or None, instance=Partner(company=company))
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة جهة الاتصال")
        return redirect("partner_list")
    return _render_form(request, code="contacts", title="جهة اتصال جديدة", form=form, back_url="partner_list")


@module_required("contacts")
def partner_edit(request, pk):
    partner = get_object_or_404(Partner, pk=pk, company=request.user.company)
    form = PartnerForm(request.POST or None, instance=partner)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديلات")
        return redirect("partner_list")
    return _render_form(request, code="contacts", title=partner.name, form=form, back_url="partner_list")


@module_required("inventory")
def product_create(request):
    company = request.user.company
    form = ProductForm(request.POST or None, instance=Product(company=company))
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error("code", "الكود أو الباركود موجود قبل كده")
        else:
            messages.success(request, "تم إضافة الصنف")
            return redirect("product_list")
    return _render_form(request, code="inventory", title="صنف جديد", form=form, back_url="product_list")


@module_required("inventory")
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.user.company)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error("code", "الكود أو الباركود موجود قبل كده")
        else:
            messages.success(request, "تم حفظ التعديلات")
            return redirect("product_detail", pk=pk)
    return _render_form(request, code="inventory", title=product.name, form=form, back_url="product_list")


@module_required("sales")
def sales_create(request):
    company = request.user.company
    order = SalesOrder(company=company, number="")
    form = SalesOrderForm(request.POST or None, instance=order, company=company)
    formset = SalesLineFormSet(request.POST or None, instance=order, form_kwargs={"company": company})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            order = form.save(commit=False)
            order.company = company
            _save_with_number(order, "sales")
            formset.instance = order
            formset.save()
        messages.success(request, f"تم إنشاء أمر البيع {order.number}")
        return redirect("sales_orders")
    return _render_form(request, code="sales", title="أمر بيع جديد", form=form, formset=formset, back_url="sales_orders")


@module_required("sales")
def sales_edit(request, pk):
    company = request.user.company
    order = get_object_or_404(SalesOrder, pk=pk, company=company)
    if order.status == "delivered":
        messages.error(request, "الأمر اتسلّم، مينفعش تتعدل")
        return redirect("sales_detail", pk=pk)
    form = SalesOrderForm(request.POST or None, instance=order, company=company)
    formset = SalesLineFormSet(request.POST or None, instance=order, form_kwargs={"company": company})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
        messages.success(request, f"تم حفظ {order.number}")
        return redirect("sales_detail", pk=pk)
    return _render_form(request, code="sales", title=order.number, form=form, formset=formset, back_url="sales_orders")


@module_required("purchasing")
def purchase_create(request):
    company = request.user.company
    order = PurchaseOrder(company=company, number="")
    form = PurchaseOrderForm(request.POST or None, instance=order, company=company)
    formset = PurchaseLineFormSet(request.POST or None, instance=order, form_kwargs={"company": company})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            order = form.save(commit=False)
            order.company = company
            _save_with_number(order, "purchasing")
            formset.instance = order
            formset.save()
        messages.success(request, f"تم إنشاء أمر الشراء {order.number}")
        return redirect("purchase_orders")
    return _render_form(request, code="purchasing", title="أمر شراء جديد", form=form, formset=formset, back_url="purchase_orders")


@module_required("purchasing")
def purchase_edit(request, pk):
    company = request.user.company
    order = get_object_or_404(PurchaseOrder, pk=pk, company=company)
    if order.status in ("received", "cancelled"):
        messages.error(request, "الأمر اتستلم، مينفعش يتعدل" if order.status == "received" else "الأمر ملغي، مينفعش يتعدل")
        return redirect("purchase_detail", pk=pk)
    form = PurchaseOrderForm(request.POST or None, instance=order, company=company)
    formset = PurchaseLineFormSet(request.POST or None, instance=order, form_kwargs={"company": company})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
        messages.success(request, f"تم حفظ {order.number}")
        return redirect("purchase_detail", pk=pk)
    return _render_form(request, code="purchasing", title=order.number, form=form, formset=formset, back_url="purchase_orders")


# ================= الإعدادات =================
def _is_manager(user):
    return user.is_superuser or user.is_company_manager


@module_required("settings")
def settings_index(request):
    if not _is_manager(request.user):
        raise PermissionDenied
    company = request.user.company
    enabled = set(CompanyModule.objects.filter(company=company, enabled=True).values_list("module__code", flat=True))
    cards = []
    for m in Module.objects.filter(code__in=enabled).order_by("sort", "name"):
        if m.code in SCHEMA:
            cards.append({"code": m.code, "name": m.name, "icon": svg_for(m.code),
                          "count": len(SCHEMA[m.code]), "c1": PALETTE[len(cards) % len(PALETTE)][0],
                          "c2": PALETTE[len(cards) % len(PALETTE)][1]})
    return render(request, "settings_index.html", {"cards": cards, "company": company})


@module_required("settings")
def settings_module(request, code):
    if not _is_manager(request.user) or code not in SCHEMA:
        raise PermissionDenied
    company = request.user.company
    module = get_object_or_404(Module, code=code)
    if request.method == "POST":
        form = build_form(code, data=request.POST, company=company)
        if form.is_valid():
            save_values(company, code, form.cleaned_data)
            messages.success(request, "تم حفظ الإعدادات")
            return redirect("settings_module", code=code)
    else:
        form = build_form(code, company=company)
    return render(request, "settings_module.html", {"form": form, "groups": grouped(code, form), "module": module, "icon": svg_for(code)})
