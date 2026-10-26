from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum

from .models import Product, StockMove


class StockError(Exception):
    pass


def on_hand(company, product, warehouse):
    total = StockMove.objects.filter(company=company, product=product, warehouse=warehouse)\
        .aggregate(t=Sum("qty"))["t"]
    return total or Decimal("0")


def total_on_hand(company, product):
    """رصيد الصنف في كل المخازن."""
    total = StockMove.objects.filter(company=company, product=product).aggregate(t=Sum("qty"))["t"]
    return total or Decimal("0")


@transaction.atomic
def post_move(*, company, product, warehouse, qty, kind, reference="", user=None, allow_negative=False):
    if warehouse is None:
        raise StockError("لازم تحدد المخزن")
    qty = Decimal(qty)
    if qty == 0:
        raise StockError("الكمية لازم تكون أكبر من صفر")
    if product.company_id != company.id or warehouse.company_id != company.id:
        raise StockError("الصنف أو المخزن مش تبع الشركة دي")
    # قفل صف الصنف عشان عمليتين في نفس اللحظة ما يصرفوش نفس الكمية
    Product.objects.select_for_update().get(pk=product.pk)
    if qty < 0 and not allow_negative and on_hand(company, product, warehouse) + qty < 0:
        raise StockError(f"الرصيد مش كافي لصنف {product.name}")
    return StockMove.objects.create(company=company, product=product, warehouse=warehouse,
                                    qty=qty, kind=kind, reference=reference, created_by=user)


def receive(*, company, product, warehouse, qty, reference="", user=None):
    return post_move(company=company, product=product, warehouse=warehouse,
                     qty=abs(Decimal(qty)), kind="receipt", reference=reference, user=user)


def issue(*, company, product, warehouse, qty, reference="", user=None, allow_negative=False):
    return post_move(company=company, product=product, warehouse=warehouse,
                     qty=-abs(Decimal(qty)), kind="issue", reference=reference, user=user,
                     allow_negative=allow_negative)


@transaction.atomic
def update_average_cost(*, company, product, qty, unit_cost):
    """متوسط التكلفة المرجح: لازم يتنادى قبل تسجيل حركة الاستلام.
    التكلفة الجديدة = (الرصيد الحالي × التكلفة الحالية + الوارد × تكلفته) ÷ (الرصيد + الوارد)."""
    qty = Decimal(qty)
    unit_cost = Decimal(unit_cost)
    if qty <= 0:
        return
    product = Product.objects.select_for_update().get(pk=product.pk, company=company)
    current = total_on_hand(company, product)
    if current <= 0:
        new_cost = unit_cost
    else:
        new_cost = (current * product.cost + qty * unit_cost) / (current + qty)
    product.cost = new_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    product.save(update_fields=["cost", "updated_at"])
