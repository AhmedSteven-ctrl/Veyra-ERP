"""شاشات مديول المشتريات الإضافية: اتفاقيات الشراء، الموردين، المنتجات، تقرير الشراء،
والتهيئة (الإعدادات، أسعار المورد، الخصائص، الفئات، الوحدات والتغليف)."""
import datetime
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, ProtectedError, transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.decorators import module_required
from core.icons import svg_for
from core.models import Partner
from core.views import (MENUS, MODULE_TITLES, _is_manager, _list_page, _render_form, _save_with_number,
                        _settings_screen, _steps)
from inventory.forms import (AttributeForm, AttributeValueFormSet, CategoryForm, PackagingForm, ProductForm,
                             UomForm)
from inventory.models import (Packaging, Product, ProductAttribute, ProductAttributeValue, ProductCategory,
                              Uom)

from .forms import AgreementForm, AgreementLineFormSet, SupplierPriceForm, VendorForm
from .models import (PurchaseAgreement, PurchaseLine, PurchaseOrder, PurchasePayment, SupplierPrice)
from .services import (activate_agreement, agreement_order_lines, cancel_agreement, close_agreement)

CODE = "purchasing"


def _render_detail(request, *, title, obj, fields, tables=(), actions=(), edit_url=None, steps=()):
    return render(request, "detail.html", {
        "code": CODE, "title": title, "module_title": MODULE_TITLES[CODE], "obj": obj, "fields": fields,
        "edit_url": edit_url, "actions": list(actions), "tables": list(tables), "steps": list(steps),
        "lines": None, "line_cols": [], "extra": [], "menus": MENUS[CODE], "icon": svg_for(CODE),
    })


# ====================================================================================
# شاشات تهيئة بسيطة (قايمة / جديد / تعديل / حذف) لأي موديل تابع للشركة
# ====================================================================================
class ConfigScreens:
    def __init__(self, *, model, form, title, new_title, columns, cells, urls, select=None, status_of=None,
                 statuses=None, creates=None, defaults=None, queryset_filter=None, block_delete=None,
                 formset=None, formset_title=None, formset_hint=None, edit_title=None):
        self.model, self.form, self.title, self.new_title = model, form, title, new_title
        self.columns, self.cells, self.urls = columns, cells, urls
        self.select, self.status_of, self.statuses, self.creates = select, status_of, statuses or [], creates
        self.defaults = defaults or {}
        self.queryset_filter = queryset_filter or {}
        self.block_delete = block_delete
        self.formset, self.formset_title, self.formset_hint = formset, formset_title, formset_hint
        self.edit_title = edit_title or (lambda obj: str(obj))

    def queryset(self, company):
        qs = self.model.objects.filter(company=company, **self.queryset_filter)
        return self.select(qs) if self.select else qs

    def list_view(self):
        @module_required(CODE)
        def view(request):
            rows = [{"id": o.id, "s": self.status_of(o) if self.status_of else "", "detail": self.urls["edit"],
                     "cells": self.cells(o)} for o in self.queryset(request.user.company)]
            return _list_page(request, code=CODE, title=self.title, rows=rows, columns=self.columns,
                              statuses=self.statuses, create=self.urls["create"], creates=self.creates)
        return view

    def _save(self, request, form, formset):
        """بيحفظ الفورم والـ formset في معاملة واحدة. بيرجّع False لو فيه تكرار اتكشف وقت الحفظ."""
        try:
            with transaction.atomic():
                obj = form.save()
                if formset is not None:
                    formset.instance = obj
                    formset.save()
        except IntegrityError:
            form.add_error(None, "البيانات دي موجودة قبل كده")
            return False
        return True

    def _page(self, request, *, title, form, formset, obj=None):
        return _render_form(request, code=CODE, title=title, form=form, formset=formset, back_url=self.urls["list"],
                            delete_url=self.urls.get("delete") if obj is not None else None, obj=obj,
                            formset_title=self.formset_title, formset_hint=self.formset_hint)

    def create_view(self):
        @module_required(CODE)
        def view(request):
            company = request.user.company
            obj = self.model(company=company, **self.defaults)
            form = self.form(request.POST or None, instance=obj, company=company)
            formset = self.formset(request.POST or None, instance=obj) if self.formset else None
            if request.method == "POST" and form.is_valid() and (formset is None or formset.is_valid()):
                if self._save(request, form, formset):
                    messages.success(request, "تم الحفظ")
                    return redirect(self.urls["list"])
            return self._page(request, title=self.new_title, form=form, formset=formset)
        return view

    def edit_view(self):
        @module_required(CODE)
        def view(request, pk):
            company = request.user.company
            obj = get_object_or_404(self.queryset(company), pk=pk)
            form = self.form(request.POST or None, instance=obj, company=company)
            formset = self.formset(request.POST or None, instance=obj) if self.formset else None
            if request.method == "POST" and form.is_valid() and (formset is None or formset.is_valid()):
                if self._save(request, form, formset):
                    messages.success(request, "تم حفظ التعديلات")
                    return redirect(self.urls["list"])
            return self._page(request, title=self.edit_title(obj), form=form, formset=formset, obj=obj)
        return view

    def delete_view(self):
        @module_required(CODE)
        @require_POST
        def view(request, pk):
            obj = get_object_or_404(self.queryset(request.user.company), pk=pk)
            problem = self.block_delete(obj) if self.block_delete else None
            if problem:
                messages.error(request, problem)
            else:
                try:
                    obj.delete()
                except ProtectedError:
                    messages.error(request, "مينفعش يتمسح لأنه مستخدم في بيانات تانية")
                else:
                    messages.success(request, "تم الحذف")
            return redirect(self.urls["list"])
        return view


# ---------- قوائم أسعار المورد ----------
_prices = ConfigScreens(
    model=SupplierPrice, form=SupplierPriceForm, title="قوائم أسعار المورد", new_title="سعر مورد جديد",
    columns=["المورد", "المنتج", "أقل كمية", "السعر", "ساري من", "ساري لحد"],
    cells=lambda o: [o.supplier.name, o.product.name, o.min_qty, o.price, o.valid_from or "—", o.valid_to or "—"],
    status_of=lambda o: o.status_on(),
    statuses=[("active", "ساري"), ("upcoming", "لسه ما بدأ"), ("expired", "منتهي")],
    select=lambda qs: qs.select_related("supplier", "product"),
    urls={"list": "supplier_price_list", "create": "supplier_price_create", "edit": "supplier_price_edit",
          "delete": "supplier_price_delete"},
    edit_title=lambda o: f"{o.supplier.name} - {o.product.name}")
supplier_price_list, supplier_price_create = _prices.list_view(), _prices.create_view()
supplier_price_edit, supplier_price_delete = _prices.edit_view(), _prices.delete_view()

# ---------- الفئات ----------
_categories = ConfigScreens(
    model=ProductCategory, form=CategoryForm, title="الفئات", new_title="فئة جديدة",
    columns=["الفئة", "الفئة الأم", "عدد المنتجات"],
    cells=lambda o: [o.full_name, o.parent.name if o.parent_id else "—", o.n],
    select=lambda qs: qs.select_related("parent").annotate(n=Count("products")),
    urls={"list": "category_list", "create": "category_create", "edit": "category_edit", "delete": "category_delete"},
    edit_title=lambda o: o.full_name)
category_list, category_create = _categories.list_view(), _categories.create_view()
category_edit, category_delete = _categories.edit_view(), _categories.delete_view()

# ---------- الخصائص (بقيمها) ----------
_attributes = ConfigScreens(
    model=ProductAttribute, form=AttributeForm, title="الخصائص", new_title="خاصية جديدة",
    columns=["الخاصية", "القيم"], cells=lambda o: [o.name, "، ".join(v.name for v in o.values.all()) or "—"],
    select=lambda qs: qs.prefetch_related("values"),
    urls={"list": "attribute_list", "create": "attribute_create", "edit": "attribute_edit",
          "delete": "attribute_delete"},
    formset=AttributeValueFormSet, formset_title="قيم الخاصية",
    formset_hint="سيب الصفوف الفاضية، ولو عايز قيم أكتر احفظ وارجع عدّل.",
    block_delete=lambda o: ("الخاصية مستخدمة في منتجات، شيلها من المنتجات الأول"
                            if ProductAttributeValue.objects.filter(attribute=o, products__isnull=False).exists()
                            else None),
    edit_title=lambda o: o.name)

# ---------- الوحدات والتغليف (شاشة واحدة فيها الاتنين) ----------
_uoms = ConfigScreens(
    model=Uom, form=UomForm, title="الوحدات والتغليف", new_title="وحدة قياس جديدة", columns=[], cells=lambda o: [],
    urls={"list": "uom_list", "create": "uom_create", "edit": "uom_edit", "delete": "uom_delete"},
    edit_title=lambda o: o.name)
uom_create, uom_edit, uom_delete = _uoms.create_view(), _uoms.edit_view(), _uoms.delete_view()

_packagings = ConfigScreens(
    model=Packaging, form=PackagingForm, title="الوحدات والتغليف", new_title="تغليف جديد", columns=[],
    cells=lambda o: [], select=lambda qs: qs.select_related("product"),
    urls={"list": "uom_list", "create": "packaging_create", "edit": "packaging_edit", "delete": "packaging_delete"},
    edit_title=lambda o: str(o))
packaging_create, packaging_edit = _packagings.create_view(), _packagings.edit_view()
packaging_delete = _packagings.delete_view()


def _plain(number):
    return format(number.normalize(), "f")


@module_required(CODE)
def uom_list(request):
    company = request.user.company
    rows = [{"id": u.id, "s": "uom", "detail": "uom_edit",
             "cells": [u.name, "وحدة قياس", f"{u.group or '—'} · {_plain(u.ratio)}"]}
            for u in Uom.objects.filter(company=company)]
    rows += [{"id": p.id, "s": "packaging", "detail": "packaging_edit", "search": p.barcode,
              "cells": [p.name, "تغليف", f"{p.product.name} · {_plain(p.qty)}" + (f" · {p.barcode}" if p.barcode else "")]}
             for p in Packaging.objects.filter(company=company).select_related("product")]
    return _list_page(request, code=CODE, title="الوحدات والتغليف", rows=rows,
                      columns=["الاسم", "النوع", "التفاصيل"],
                      statuses=[("uom", "وحدات القياس"), ("packaging", "التغليف")],
                      creates=[("وحدة", "uom_create"), ("تغليف", "packaging_create")])


# ====================================================================================
# الموردين
# ====================================================================================
VENDOR_KINDS = ("supplier", "both")

_vendors = ConfigScreens(
    model=Partner, form=VendorForm, title="الموردين", new_title="مورد جديد", columns=[], cells=lambda o: [],
    defaults={"kind": "supplier"}, queryset_filter={"kind__in": VENDOR_KINDS},
    urls={"list": "vendor_list", "create": "vendor_create", "edit": "vendor_edit"}, edit_title=lambda o: o.name)
vendor_create, vendor_edit = _vendors.create_view(), _vendors.edit_view()


def _vendor_figures(company, supplier_id=None):
    """(المستحق الكلي، المدفوع، عدد الأوامر) لكل مورد: قواميس بمفتاح رقم المورد."""
    def only(qs, field):
        return qs.filter(**{field: supplier_id}) if supplier_id else qs

    received = only(PurchaseOrder.objects.filter(company=company, status="received"), "supplier_id")
    billed = {r["supplier"]: r["t"] for r in received.order_by().values("supplier").annotate(t=Sum("billed_total"))}
    payments = only(PurchasePayment.objects.filter(order__company=company), "order__supplier_id")
    paid = {r["order__supplier"]: r["t"] for r in payments.order_by().values("order__supplier").annotate(t=Sum("amount"))}
    live = only(PurchaseOrder.objects.filter(company=company).exclude(status__in=("draft", "cancelled")), "supplier_id")
    counts = {r["supplier"]: r["n"] for r in live.order_by().values("supplier").annotate(n=Count("id"))}
    return billed, paid, counts


@module_required(CODE)
def vendor_list(request):
    company = request.user.company
    billed, paid, counts = _vendor_figures(company)
    rows = [{"id": v.id, "s": v.kind, "detail": "vendor_detail",
             "cells": [v.name, v.phone or "—", v.city or "—", counts.get(v.id, 0),
                       billed.get(v.id, Decimal("0")) - paid.get(v.id, Decimal("0"))]}
            for v in Partner.objects.filter(company=company, kind__in=VENDOR_KINDS)]
    return _list_page(request, code=CODE, title="الموردين", rows=rows,
                      columns=["الاسم", "الهاتف", "المدينة", "عدد الأوامر", "المستحق للمورد"],
                      statuses=[("supplier", "مورد"), ("both", "عميل ومورد")], create="vendor_create")


@module_required(CODE)
def vendor_detail(request, pk):
    company = request.user.company
    vendor = get_object_or_404(Partner, pk=pk, company=company, kind__in=VENDOR_KINDS)
    billed, paid, counts = _vendor_figures(company, vendor.id)
    total_billed, total_paid = billed.get(vendor.id, Decimal("0")), paid.get(vendor.id, Decimal("0"))
    fields = [("الاسم", vendor.name), ("النوع", vendor.get_kind_display()), ("الهاتف", vendor.phone or "—"),
              ("المدينة", vendor.city or "—"), ("عدد الأوامر", counts.get(vendor.id, 0)),
              ("إجمالي المستلم", total_billed), ("المدفوع", total_paid), ("المستحق للمورد", total_billed - total_paid)]
    status_labels = dict(PurchaseOrder.STATUS)
    tables = []
    orders = [(o.number, status_labels[o.status], o.total) for o in vendor.purchase_orders.all()[:20]]
    if orders:
        tables.append({"title": "آخر الأوامر", "cols": ["الرقم", "الحالة", "الإجمالي"], "rows": orders})
    prices = [(p.product.name, p.min_qty, p.price, p.valid_from or "—", p.valid_to or "—")
              for p in vendor.supplier_prices.select_related("product")]
    if prices:
        tables.append({"title": "قايمة أسعار المورد", "cols": ["المنتج", "أقل كمية", "السعر", "ساري من", "ساري لحد"],
                       "rows": prices})
    agreements = [(a.number, dict(PurchaseAgreement.STATUS)[a.status], a.total) for a in vendor.agreements.all()]
    if agreements:
        tables.append({"title": "اتفاقيات الشراء", "cols": ["الرقم", "الحالة", "الإجمالي"], "rows": agreements})
    return _render_detail(request, title=vendor.name, obj=vendor, fields=fields, tables=tables, edit_url="vendor_edit")


# ====================================================================================
# المنتجات (من جوه المشتريات)
# ====================================================================================
@module_required(CODE)
def purchase_products(request):
    company = request.user.company
    products = (Product.objects.filter(company=company).select_related("category")
                .annotate(stock=Coalesce(Sum("stock_moves__qty"), Decimal("0"))))
    rows = [{"id": p.id, "s": f"c{p.category_id}" if p.category_id else "none", "detail": "purchase_product_detail",
             "cells": [p.code, p.name, p.category.full_name if p.category_id else "—", p.barcode or "—", p.cost, p.stock],
             "search": p.barcode}
            for p in products]
    statuses = [(f"c{c.id}", c.full_name) for c in ProductCategory.objects.filter(company=company)]
    statuses.append(("none", "بدون فئة"))
    return _list_page(request, code=CODE, title="المنتجات", rows=rows,
                      columns=["الكود", "المنتج", "الفئة", "الباركود", "التكلفة", "الرصيد"],
                      statuses=statuses, create="purchase_product_create")


@module_required(CODE)
def purchase_product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.user.company)
    stock = product.stock_moves.aggregate(t=Sum("qty"))["t"] or Decimal("0")
    fields = [("الكود", product.code), ("الاسم", product.name), ("الباركود", product.barcode or "—"),
              ("الفئة", product.category.full_name if product.category_id else "—"), ("الوحدة", product.unit),
              ("تكلفة الوحدة", product.cost), ("سعر البيع", product.sale_price), ("الرصيد الحالي", stock),
              ("الخصائص", "، ".join(str(v) for v in product.attribute_values.select_related("attribute")) or "—")]
    tables = []
    prices = [(p.supplier.name, p.min_qty, p.price, p.valid_from or "—", p.valid_to or "—")
              for p in product.supplier_prices.select_related("supplier")]
    if prices:
        tables.append({"title": "أسعار الموردين", "cols": ["المورد", "أقل كمية", "السعر", "ساري من", "ساري لحد"],
                       "rows": prices})
    packs = [(p.name, p.qty, p.barcode or "—") for p in product.packagings.all()]
    if packs:
        tables.append({"title": "التغليف", "cols": ["الاسم", "الكمية في العبوة", "الباركود"], "rows": packs})
    return _render_detail(request, title=product.name, obj=product, fields=fields, tables=tables,
                          edit_url="purchase_product_edit")


def _product_form_page(request, product, *, title):
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        try:
            saved = form.save()
        except IntegrityError:
            form.add_error("code", "الكود أو الباركود موجود قبل كده")
        else:
            messages.success(request, "تم الحفظ")
            return redirect("purchase_product_detail", pk=saved.pk)
    return _render_form(request, code=CODE, title=title, form=form, back_url="purchase_products")


@module_required(CODE)
def purchase_product_create(request):
    return _product_form_page(request, Product(company=request.user.company), title="منتج جديد")


@module_required(CODE)
def purchase_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.user.company)
    return _product_form_page(request, product, title=product.name)


# ====================================================================================
# اتفاقيات الشراء
# ====================================================================================
AGREEMENT_STEPS = [("draft", "مسودة"), ("active", "ساري"), ("closed", "مغلق")]
AGREEMENT_LIST_ACTIONS = {"draft": ("agreement_activate", "تفعيل"), "active": ("agreement_make_order", "إنشاء طلب شراء")}


def _agreement_actions(agreement):
    actions = []
    if agreement.status == "draft":
        actions.append({"url": "agreement_activate", "label": "تفعيل الاتفاقية", "post": True})
    if agreement.status == "active":
        actions.append({"url": "agreement_make_order", "label": "إنشاء طلب شراء", "post": True})
        actions.append({"url": "agreement_close", "label": "إغلاق الاتفاقية", "post": True,
                        "confirm": "هتقفل الاتفاقية دي. متأكد؟"})
    if agreement.status in ("draft", "active"):
        actions.append({"url": "agreement_cancel", "label": "إلغاء الاتفاقية", "post": True,
                        "confirm": "هتلغي الاتفاقية دي. متأكد؟"})
    return actions


@module_required(CODE)
def agreement_list(request):
    agreements = PurchaseAgreement.objects.filter(company=request.user.company).select_related("supplier")
    rows = [{"id": a.id, "s": a.status, "detail": "agreement_detail", "action": AGREEMENT_LIST_ACTIONS.get(a.status),
             "cells": [a.number, a.supplier.name, f"{a.start_date} → {a.end_date or '—'}", a.total]}
            for a in agreements]
    return _list_page(request, code=CODE, title="اتفاقيات الشراء", rows=rows,
                      columns=["الرقم", "المورد", "الفترة", "الإجمالي"], statuses=list(PurchaseAgreement.STATUS),
                      create="agreement_create")


@module_required(CODE)
def agreement_detail(request, pk):
    agreement = get_object_or_404(PurchaseAgreement, pk=pk, company=request.user.company)
    fields = [("الرقم", agreement.number), ("المورد", agreement.supplier.name),
              ("الحالة", agreement.get_status_display()),
              ("الفترة", f"{agreement.start_date} → {agreement.end_date or '—'}"),
              ("إجمالي الاتفاقية", agreement.total)]
    if agreement.notes:
        fields.append(("ملاحظات", agreement.notes))
    lines = [(l.product.name, l.qty, l.price, l.ordered, l.remaining)
             for l in agreement.lines.select_related("product")]
    tables = [{"title": "الأصناف", "cols": ["الصنف", "المتفق عليه", "السعر", "اتطلب", "المتبقي"], "rows": lines}]
    status_labels = dict(PurchaseOrder.STATUS)
    orders = [(o.number, status_labels[o.status], o.total) for o in agreement.orders.all()]
    if orders:
        tables.append({"title": "الطلبات المرتبطة", "cols": ["الرقم", "الحالة", "الإجمالي"], "rows": orders})
    return _render_detail(request, title=agreement.number, obj=agreement, fields=fields, tables=tables,
                          actions=_agreement_actions(agreement),
                          edit_url="agreement_edit" if agreement.status == "draft" else None,
                          steps=[] if agreement.status == "cancelled" else _steps(AGREEMENT_STEPS, agreement.status))


@module_required(CODE)
def agreement_create(request):
    company = request.user.company
    agreement = PurchaseAgreement(company=company, number="")
    form = AgreementForm(request.POST or None, instance=agreement, company=company)
    formset = AgreementLineFormSet(request.POST or None, instance=agreement, form_kwargs={"company": company})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            agreement = form.save(commit=False)
            agreement.company = company
            _save_with_number(agreement, "agreement")
            formset.instance = agreement
            formset.save()
        messages.success(request, f"تم إنشاء الاتفاقية {agreement.number}")
        return redirect("agreement_detail", pk=agreement.pk)
    return _render_form(request, code=CODE, title="اتفاقية شراء جديدة", form=form, formset=formset,
                        back_url="agreement_list", formset_title="أصناف الاتفاقية",
                        formset_hint="لإضافة صنف جديد احفظ الاتفاقية، وبعدها ارجع عدّل وضيف الصنف التاني.")


@module_required(CODE)
def agreement_edit(request, pk):
    company = request.user.company
    agreement = get_object_or_404(PurchaseAgreement, pk=pk, company=company)
    if agreement.status != "draft":
        messages.error(request, "الاتفاقية بعد التفعيل مينفعش تتعدل")
        return redirect("agreement_detail", pk=pk)
    form = AgreementForm(request.POST or None, instance=agreement, company=company)
    formset = AgreementLineFormSet(request.POST or None, instance=agreement, form_kwargs={"company": company})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
        messages.success(request, f"تم حفظ {agreement.number}")
        return redirect("agreement_detail", pk=pk)
    return _render_form(request, code=CODE, title=agreement.number, form=form, formset=formset,
                        back_url="agreement_list", formset_title="أصناف الاتفاقية",
                        formset_hint="لإضافة صنف جديد احفظ الاتفاقية، وبعدها ارجع عدّل وضيف الصنف التاني.")


def _agreement_transition(request, pk, action, done):
    agreement = get_object_or_404(PurchaseAgreement, pk=pk, company=request.user.company)
    try:
        action(agreement)
        messages.success(request, done.format(number=agreement.number))
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("agreement_detail", pk=pk)


@module_required(CODE)
@require_POST
def agreement_activate(request, pk):
    return _agreement_transition(request, pk, activate_agreement, "تم تفعيل الاتفاقية {number}")


@module_required(CODE)
@require_POST
def agreement_close(request, pk):
    return _agreement_transition(request, pk, close_agreement, "تم إغلاق الاتفاقية {number}")


@module_required(CODE)
@require_POST
def agreement_cancel(request, pk):
    return _agreement_transition(request, pk, cancel_agreement, "تم إلغاء الاتفاقية {number}")


@module_required(CODE)
@require_POST
def agreement_make_order(request, pk):
    """بيعمل طلب عرض سعر (مسودة) بالكميات المتبقية من الاتفاقية وبأسعارها المتفق عليها."""
    company = request.user.company
    agreement = get_object_or_404(PurchaseAgreement, pk=pk, company=company)
    try:
        lines = agreement_order_lines(agreement)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("agreement_detail", pk=pk)
    with transaction.atomic():
        order = PurchaseOrder(company=company, supplier=agreement.supplier, status="draft", agreement=agreement)
        _save_with_number(order, "purchasing")
        for product, qty, price in lines:
            PurchaseLine.objects.create(order=order, product=product, qty=qty, cost=price)
    messages.success(request, f"تم إنشاء طلب عرض السعر {order.number} من الاتفاقية {agreement.number}")
    return redirect("purchase_detail", pk=order.pk)


# ====================================================================================
# تقرير الشراء
# ====================================================================================
REPORT_DIMENSIONS = [("supplier", "المورد"), ("product", "المنتج"), ("category", "فئة المنتج"), ("month", "الشهر")]
_REPORT_PATHS = {"supplier": "order__supplier__name", "product": "product__name", "category": "product__category__name"}


def _parse_date(value):
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


@module_required(CODE)
def purchase_report(request):
    company = request.user.company
    by = request.GET.get("by", "supplier")
    if by not in dict(REPORT_DIMENSIONS):
        by = "supplier"
    date_from, date_to = _parse_date(request.GET.get("from")), _parse_date(request.GET.get("to"))

    orders = PurchaseOrder.objects.filter(company=company, status__in=("confirmed", "received"))
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)

    amount = ExpressionWrapper(F("qty") * F("cost"), output_field=DecimalField(max_digits=20, decimal_places=5))
    group = TruncMonth("order__created_at") if by == "month" else F(_REPORT_PATHS[by])
    data = (PurchaseLine.objects.filter(order__in=orders).annotate(g=group).values("g")
            .annotate(order_count=Count("order", distinct=True), qty_sum=Sum("qty"), amount_sum=Sum(amount))
            .order_by("g" if by == "month" else "-amount_sum"))
    data = list(data)
    total = sum((r["amount_sum"] or Decimal("0") for r in data), Decimal("0"))
    cent = Decimal("0.01")
    rows = []
    for r in data:
        value = r["amount_sum"] or Decimal("0")
        rows.append({"label": r["g"].strftime("%Y-%m") if by == "month" else (r["g"] or "—"),
                     "orders": r["order_count"], "qty": r["qty_sum"], "amount": value.quantize(cent),
                     "share": int(round(value / total * 100)) if total else 0})

    received = orders.filter(status="received")
    billed = received.aggregate(t=Sum("billed_total"))["t"] or Decimal("0")
    paid = PurchasePayment.objects.filter(order__in=received).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    summary = {"orders": orders.count(), "net": total.quantize(cent), "billed": billed, "paid": paid,
               "due": billed - paid}
    return render(request, "purchase_report.html", {
        "code": CODE, "title": "تقرير الشراء", "module_title": MODULE_TITLES[CODE], "rows": rows, "summary": summary,
        "by": by, "dimensions": REPORT_DIMENSIONS, "date_from": date_from, "date_to": date_to,
        "total": total.quantize(cent), "menus": MENUS[CODE], "icon": svg_for(CODE),
    })


# ====================================================================================
# الإعدادات
# ====================================================================================
@module_required(CODE)
def purchase_settings(request):
    if not _is_manager(request.user):
        raise PermissionDenied
    return _settings_screen(request, CODE, redirect_name="purchase_settings", back_url="purchase_orders")


# أسماء الشاشات اللي بتتسجّل في الروابط
attribute_list, attribute_create = _attributes.list_view(), _attributes.create_view()
attribute_edit, attribute_delete = _attributes.edit_view(), _attributes.delete_view()
