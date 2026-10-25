from django.db import transaction

from inventory.services import issue

from .models import SalesOrder


@transaction.atomic
def deliver(order: SalesOrder, warehouse, user=None):
    """التسليم: يصرف كل أصناف الأمر من المخزن في معاملة واحدة.
    لو صنف واحد ما يكفيش، كل التسليم يترجع ومفيش حاجة تتصرف."""
    if order.status == "delivered":
        raise ValueError("الأمر اتسلّم قبل كده")
    for line in order.lines.select_related("product"):
        issue(company=order.company, product=line.product, warehouse=warehouse,
              qty=line.qty, reference=order.number, user=user)
    order.status = "delivered"
    order.save(update_fields=["status", "updated_at"])
    from accounting.services import post_sale
    post_sale(order, user=user)
    return order
