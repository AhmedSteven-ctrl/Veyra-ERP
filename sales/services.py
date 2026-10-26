from django.db import transaction
from django.utils import timezone

from core.settings_schema import current_values
from inventory.services import StockError, issue

from .models import SalesOrder


def _claim(order, *, from_status, to_status):
    """ينقل حالة الأمر في خطوة واحدة بشرط إنه لسه في الحالة المتوقعة.
    لو الزرار اتضغط مرتين، التاني بيلاقي الحالة اتغيّرت ومبيتنفذش (بيشتغل على SQLite وPostgreSQL)."""
    return SalesOrder.objects.filter(pk=order.pk, company=order.company, status=from_status)\
        .update(status=to_status, updated_at=timezone.now())


@transaction.atomic
def confirm_order(order: SalesOrder):
    """تأكيد المسودة قبل التسليم."""
    if not order.lines.exists():
        raise ValueError("الأمر مفيهوش أصناف")
    if not _claim(order, from_status="draft", to_status="confirmed"):
        order.refresh_from_db(fields=["status"])
        raise ValueError("الأمر اتسلّم قبل كده" if order.status == "delivered" else "الأمر مؤكد قبل كده")
    order.status = "confirmed"
    return order


@transaction.atomic
def deliver(order: SalesOrder, warehouse, user=None):
    """التسليم: يصرف كل أصناف الأمر من المخزن في معاملة واحدة.
    لو صنف واحد ما يكفيش، كل التسليم يترجع ومفيش حاجة تتصرف. الأمر لازم يكون مؤكد، وبيتسلّم مرة واحدة بس."""
    if warehouse is None:
        raise StockError("مفيش مخزن نسلّم منه")
    if not _claim(order, from_status="confirmed", to_status="delivered"):
        order.refresh_from_db(fields=["status"])
        raise ValueError("الأمر اتسلّم قبل كده" if order.status == "delivered" else "لازم تأكّد الأمر الأول")
    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ValueError("الأمر مفيهوش أصناف")
    allow_negative = current_values(order.company, "inventory")["allow_negative"]
    for line in lines:
        issue(company=order.company, product=line.product, warehouse=warehouse,
              qty=line.qty, reference=order.number, user=user, allow_negative=allow_negative)
    from accounting.services import post_sale
    post_sale(order, user=user)
    order.status = "delivered"
    return order
