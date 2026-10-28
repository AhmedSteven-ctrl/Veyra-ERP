from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from .models import Product, StockMove, Warehouse


class StockError(Exception):
    pass


def on_hand(company, product, warehouse):
    total = StockMove.objects.filter(company=company, product=product, warehouse=warehouse)        .aggregate(t=Sum("qty"))["t"]
    return total or Decimal("0")


@transaction.atomic
def post_move(*, company, product, warehouse, qty, kind, reference="", user=None, allow_negative=False):
    qty = Decimal(qty)
    if qty == 0:
        raise StockError("الكمية لازم تكون أكبر من صفر")
    if product.company_id != company.id or warehouse.company_id != company.id:
        raise StockError("الصنف أو المخزن مش تبع الشركة دي")
    # قفل صف الصنف عشان عمليتين في نفس اللحظة ما يصرفوش نفس الكمية
    Product.objects.select_for_update().get(pk=product.pk)
    if qty < 0 and not allow_negative and on_hand(company, product, warehouse) + qty < 0:
        raise StockError(f"الرصيد مش كافي لصنف {product.name} في مخزن {warehouse.name}")
    return StockMove.objects.create(company=company, product=product, warehouse=warehouse,
                                    qty=qty, kind=kind, reference=reference, created_by=user)


def receive(*, company, product, warehouse, qty, reference="", user=None):
    return post_move(company=company, product=product, warehouse=warehouse,
                     qty=abs(Decimal(qty)), kind="receipt", reference=reference, user=user)


def issue(*, company, product, warehouse, qty, reference="", user=None):
    return post_move(company=company, product=product, warehouse=warehouse,
                     qty=-abs(Decimal(qty)), kind="issue", reference=reference, user=user)


@transaction.atomic
def transfer_stock(*, company, product, from_warehouse, to_warehouse, qty, reference="", user=None):
    """تحويل مخزني بين مستودعين في معاملة واحدة ذرية (Atomic)"""
    qty_val = abs(Decimal(qty))
    # صرف من المخزن المحول منه
    issue(company=company, product=product, warehouse=from_warehouse, qty=qty_val, reference=f"تحويل إلى {to_warehouse.name} - {reference}", user=user)
    # استلام في المخزن المحول إليه
    receive(company=company, product=product, warehouse=to_warehouse, qty=qty_val, reference=f"تحويل من {from_warehouse.name} - {reference}", user=user)


@transaction.atomic
def adjust_stock(*, company, product, warehouse, physical_qty, reference="", user=None):
    """تسوية جردية لمطابقة الرصيد الفعلي بالدفعتي"""
    current_qty = on_hand(company, product, warehouse)
    target_qty = Decimal(physical_qty)
    diff = target_qty - current_qty
    if diff == 0:
        return None
    kind = "adjust"
    return post_move(company=company, product=product, warehouse=warehouse, qty=diff, kind=kind, reference=f"تسوية جردية: {reference}", user=user, allow_negative=True)
