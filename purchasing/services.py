from django.db import transaction
from inventory.services import receive, issue
from .models import PurchaseOrder


@transaction.atomic
def confirm_rfq(order: PurchaseOrder):
    """تأكيد طلب عرض السعر وتحويله إلى أمر شراء مؤكد"""
    if order.status not in ["draft", "sent", "unconfirmed", "late_rfq"]:
        raise ValueError("الطلب ليس في حالة تسمح بالتأكيد")
    order.status = "confirmed"
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def receive_order(order: PurchaseOrder, warehouse, user=None):
    """استلام البضاعة: يدخل كل أصناف الأمر المخزن وترحيل القيد المحاسبي."""
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


@transaction.atomic
def cancel_order(order: PurchaseOrder):
    """إلغاء أمر الشراء"""
    if order.status == "received":
        raise ValueError("لا يمكن إلغاء أمر تم استلامه بالفعل")
    order.status = "cancel"
    order.save(update_fields=["status", "updated_at"])
    return order
