from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory.models import Product, Warehouse
from inventory.services import StockError
from purchasing.models import PurchaseOrder
from purchasing.services import receive_order
from sales.models import SalesOrder
from sales.services import deliver

from .decorators import module_required
from .models import CompanyModule, Module

# الشاشات المنفذة حالياً (كود المديول -> اسم الـ URL)
IMPLEMENTED = {"inventory": "product_list", "sales": "sales_orders", "purchasing": "purchase_orders"}
ICONS = {"inventory": "📦", "sales": "🧾", "purchasing": "🛒", "accounting": "📊", "contacts": "👤", "crm": "🤝",
         "employees": "👥", "manufacturing": "🏭", "quality": "✅", "maintenance": "🔧", "settings": "⚙"}
PALETTE = [("#3D63F5", "#7A4DFF"), ("#0FAF7B", "#6EE7B7"), ("#F2A20C", "#FCD34D"), ("#E5484D", "#FCA5A5"),
           ("#0EA5E9", "#7DD3FC"), ("#8B5CF6", "#C4B5FD"), ("#64748B", "#A3B1C6"), ("#F97316", "#FDBA74")]
MENUS = {
    "inventory": [("المنتجات والأرصدة", "product_list")],
    "sales": [("أوامر البيع", "sales_orders")],
    "purchasing": [("أوامر الشراء", "purchase_orders")],
}


def _warehouse(company):
    return Warehouse.objects.filter(company=company).order_by("id").first()


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    user = request.user
    groups = []
    if user.company_id:
        enabled = set(CompanyModule.objects.filter(company_id=user.company_id, enabled=True)
                      .values_list("module__code", flat=True))
        visible = {m.code: m for m in Module.objects.filter(code__in=enabled) if user.can_access(m.code)}
        children = {}
        for m in visible.values():
            if m.parent_id and m.parent.code in visible:
                children.setdefault(m.parent.code, []).append(m)
        for i, m in enumerate(sorted((m for m in visible.values() if not (m.parent_id and m.parent.code in visible)),
                                     key=lambda x: (x.sort, x.name))):
            c1, c2 = PALETTE[i % len(PALETTE)]
            groups.append({"module": m, "icon": ICONS.get(m.code, "▦"), "c1": c1, "c2": c2,
                           "url": IMPLEMENTED.get(m.code), "children": children.get(m.code, [])})
    return render(request, "home.html", {"groups": groups})


def _steps(statuses, current):
    keys = [k for k, _ in statuses]
    idx = keys.index(current) if current in keys else -1
    return [{"label": l, "state": "done" if i < idx else ("cur" if i == idx else "")}
            for i, (k, l) in enumerate(statuses)]


@module_required("inventory")
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.user.company)
    stock = Coalesce(Sum("stock_moves__qty"), Decimal("0"))
    stock_now = product.stock_moves.aggregate(t=Sum("qty"))["t"] or Decimal("0")
    moves = product.stock_moves.select_related("warehouse")[:20]
    fields = [("الكود", product.code), ("الاسم", product.name), ("الوحدة", product.unit),
              ("سعر البيع", product.sale_price), ("حد إعادة الطلب", product.min_qty), ("الرصيد الحالي", stock_now)]
    return render(request, "detail.html", {
        "code": "inventory", "title": product.name, "obj": product, "fields": fields,
        "steps": [], "lines": [(m.created_at.strftime("%Y-%m-%d %H:%M"), m.warehouse.name, m.get_kind_display(), m.qty, m.reference) for m in moves],
        "line_cols": ["التاريخ", "المخزن", "النوع", "الكمية", "المرجع"], "extra": [],
        "menus": MENUS.get("inventory", []), "icon": ICONS.get("inventory"),
    })


@module_required("sales")
def sales_detail(request, pk):
    order = get_object_or_404(SalesOrder, pk=pk, company=request.user.company)
    fields = [("الرقم", order.number), ("العميل", order.customer.name), ("الإجمالي", order.total)]
    lines = [(l.product.name, l.qty, l.price, l.subtotal) for l in order.lines.select_related("product")]
    return render(request, "detail.html", {
        "code": "sales", "title": order.number, "obj": order, "fields": fields,
        "steps": _steps(SalesOrder.STATUS, order.status), "lines": lines,
        "line_cols": ["الصنف", "الكمية", "السعر", "الإجمالي"], "extra": [],
        "menus": MENUS.get("sales", []), "icon": ICONS.get("sales"),
    })


@module_required("purchasing")
def purchase_detail(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    fields = [("الرقم", order.number), ("المورد", order.supplier.name), ("الإجمالي", order.total)]
    lines = [(l.product.name, l.qty, l.cost, l.subtotal) for l in order.lines.select_related("product")]
    return render(request, "detail.html", {
        "code": "purchasing", "title": order.number, "obj": order, "fields": fields,
        "steps": _steps(PurchaseOrder.STATUS, order.status), "lines": lines,
        "line_cols": ["الصنف", "الكمية", "التكلفة", "الإجمالي"], "extra": [],
        "menus": MENUS.get("purchasing", []), "icon": ICONS.get("purchasing"),
    })


def _list_page(request, *, code, title, columns, rows, statuses):
    f = request.GET.get("f", "")
    q = request.GET.get("q", "").strip()
    labels = dict(statuses)
    for r in rows:
        r["label"] = labels.get(r["s"], r["s"])
    stats = [{"key": "", "label": "الكل", "count": len(rows), "active": f == ""}]
    stats += [{"key": k, "label": l, "count": sum(1 for r in rows if r["s"] == k), "active": f == k}
              for k, l in statuses]
    shown = [r for r in rows if (not f or r["s"] == f)
             and (not q or q in " ".join(str(c) for c in r["cells"]))]
    return render(request, "list.html", {
        "code": code, "title": title, "columns": columns, "stats": stats, "rows": shown,
        "q": q, "statuses": dict(statuses), "menus": MENUS.get(code, []),
        "icon": ICONS.get(code, "▦"),
    })


@module_required("inventory")
def product_list(request):
    products = (Product.objects.filter(company=request.user.company)
                .annotate(stock=Coalesce(Sum("stock_moves__qty"), Decimal("0"))))
    rows = [{"id": p.id, "s": "low" if p.stock < p.min_qty else "ok", "detail": "product_detail",
             "cells": [p.code, p.name, p.sale_price, p.stock]} for p in products]
    return _list_page(request, code="inventory", title="المخزون", rows=rows,
                      columns=["الكود", "الصنف", "سعر البيع", "الرصيد"],
                      statuses=[("ok", "متوفر"), ("low", "تحت حد الطلب")])


@module_required("sales")
def sales_orders(request):
    orders = SalesOrder.objects.filter(company=request.user.company).select_related("customer")
    rows = [{"id": o.id, "s": o.status, "detail": "sales_detail", "cells": [o.number, o.customer.name, o.total],
             "action": ("sales_deliver", "تسليم وخصم من المخزن") if o.status != "delivered" else None}
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


@module_required("purchasing")
def purchase_orders(request):
    orders = PurchaseOrder.objects.filter(company=request.user.company).select_related("supplier")
    rows = [{"id": o.id, "s": o.status, "detail": "purchase_detail", "cells": [o.number, o.supplier.name, o.total],
             "action": ("purchase_receive", "استلام وإدخال للمخزن") if o.status != "received" else None}
            for o in orders]
    return _list_page(request, code="purchasing", title="الشراء", rows=rows,
                      columns=["الرقم", "المورد", "الإجمالي"],
                      statuses=[("draft", "مسودة"), ("confirmed", "بانتظار الاستلام"), ("received", "مستلم")])


@module_required("purchasing")
@require_POST
def purchase_receive(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    try:
        receive_order(order, _warehouse(request.user.company), user=request.user)
        messages.success(request, f"تم استلام الأمر {order.number} وإضافته للمخزن")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchase_orders")
