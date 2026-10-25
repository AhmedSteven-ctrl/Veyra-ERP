from django.db import transaction

from inventory.services import receive

from .models import PurchaseOrder


@transaction.atomic
def receive_order(order: PurchaseOrder, warehouse, user=None):
    """استلام البضاعة: يدخل كل أصناف الأمر المخزن في معاملة واحدة."""
    if order.status == "received":
        raise ValueError("الأمر اتستلم قبل كده")
    for line in order.lines.select_related("product"):
        receive(company=order.company, product=line.product, warehouse=warehouse,
                qty=line.qty, reference=order.number, user=user)
    order.status = "received"
    order.save(update_fields=["status", "updated_at"])
    from accounting.services import post_purchase
    post_purchase(order, user=user)
    return order
