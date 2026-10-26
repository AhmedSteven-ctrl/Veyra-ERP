from django.db import transaction
from django.utils import timezone

from inventory.services import StockError, receive, update_average_cost

from .models import PurchaseOrder


def _claim(order, *, from_status, to_status):
    """نفس فكرة المبيعات: نقل الحالة في خطوة واحدة بشرط إنها لسه زي ما هي، عشان الاستلام ما يتكررش."""
    return PurchaseOrder.objects.filter(pk=order.pk, company=order.company, status=from_status)\
        .update(status=to_status, updated_at=timezone.now())


@transaction.atomic
def confirm_order(order: PurchaseOrder):
    """تأكيد المسودة قبل الاستلام."""
    if not order.lines.exists():
        raise ValueError("الأمر مفيهوش أصناف")
    if not _claim(order, from_status="draft", to_status="confirmed"):
        order.refresh_from_db(fields=["status"])
        raise ValueError("الأمر اتستلم قبل كده" if order.status == "received" else "الأمر مؤكد قبل كده")
    order.status = "confirmed"
    return order


@transaction.atomic
def receive_order(order: PurchaseOrder, warehouse, user=None):
    """استلام البضاعة: يدخل كل أصناف الأمر المخزن في معاملة واحدة، ويحدّث متوسط تكلفة كل صنف."""
    if warehouse is None:
        raise StockError("مفيش مخزن نستلم فيه")
    if not _claim(order, from_status="confirmed", to_status="received"):
        order.refresh_from_db(fields=["status"])
        raise ValueError("الأمر اتستلم قبل كده" if order.status == "received" else "لازم تأكّد الأمر الأول")
    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ValueError("الأمر مفيهوش أصناف")
    for line in lines:
        update_average_cost(company=order.company, product=line.product, qty=line.qty, unit_cost=line.cost)
        receive(company=order.company, product=line.product, warehouse=warehouse,
                qty=line.qty, reference=order.number, user=user)
    from accounting.services import post_purchase
    post_purchase(order, user=user)
    order.status = "received"
    return order
