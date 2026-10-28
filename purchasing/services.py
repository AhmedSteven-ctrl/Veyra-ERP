from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from inventory.services import StockError, receive, update_average_cost

from .models import PurchaseOrder, PurchasePayment


def _claim(order, *, from_status, to_status):
    """ينقل حالة الأمر في خطوة واحدة بشرط إنه لسه في الحالة المتوقعة (حالة واحدة أو أكتر).
    لو الزرار اتضغط مرتين، التاني بيلاقي الحالة اتغيّرت ومبيتنفذش (بيشتغل على SQLite وPostgreSQL)."""
    statuses = (from_status,) if isinstance(from_status, str) else tuple(from_status)
    return PurchaseOrder.objects.filter(pk=order.pk, company=order.company, status__in=statuses)\
        .update(status=to_status, updated_at=timezone.now())


def _why_not(order, action):
    """سبب رفض الإجراء حسب الحالة الحالية للأمر في القاعدة (action: confirm / receive / cancel)."""
    order.refresh_from_db(fields=["status"])
    status = order.status
    if status == "cancelled":
        return "الأمر ملغي قبل كده" if action == "cancel" else "الأمر ملغي"
    if status == "received":
        return "الأمر اتستلم، مينفعش يتلغي" if action == "cancel" else "الأمر اتستلم قبل كده"
    if status == "confirmed" and action == "confirm":
        return "الأمر مؤكد قبل كده"
    if status == "draft" and action == "receive":
        return "لازم تأكّد الأمر الأول"
    return "الإجراء ده مش متاح على الأمر في حالته الحالية"


@transaction.atomic
def confirm_order(order: PurchaseOrder):
    """تأكيد المسودة قبل الاستلام."""
    if not order.lines.exists():
        raise ValueError("الأمر مفيهوش أصناف")
    if not _claim(order, from_status="draft", to_status="confirmed"):
        raise ValueError(_why_not(order, "confirm"))
    order.status = "confirmed"
    return order


@transaction.atomic
def cancel_order(order: PurchaseOrder):
    """إلغاء أمر لسه ما اتستلمش (مسودة أو مؤكد). الأمر المستلم عليه حركات مخزن وقيد، فمينفعش يتلغي."""
    if not _claim(order, from_status=("draft", "confirmed"), to_status="cancelled"):
        raise ValueError(_why_not(order, "cancel"))
    order.status = "cancelled"
    return order


@transaction.atomic
def receive_order(order: PurchaseOrder, warehouse, user=None):
    """استلام البضاعة: يدخل كل أصناف الأمر المخزن، ويحدّث متوسط تكلفة كل صنف، ويسجّل القيد
    ويحفظ المستحق للمورد (billed_total)، كل ده في معاملة واحدة."""
    if warehouse is None:
        raise StockError("مفيش مخزن نستلم فيه")
    if not _claim(order, from_status="confirmed", to_status="received"):
        raise ValueError(_why_not(order, "receive"))
    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ValueError("الأمر مفيهوش أصناف")
    for line in lines:
        update_average_cost(company=order.company, product=line.product, qty=line.qty, unit_cost=line.cost)
        receive(company=order.company, product=line.product, warehouse=warehouse,
                qty=line.qty, reference=order.number, user=user)
    from accounting.services import post_purchase, purchase_amounts
    amounts = purchase_amounts(order)
    post_purchase(order, user=user, amounts=amounts)
    PurchaseOrder.objects.filter(pk=order.pk).update(billed_total=amounts[2], updated_at=timezone.now())
    order.billed_total = amounts[2]
    order.status = "received"
    return order


@transaction.atomic
def pay_order(order: PurchaseOrder, amount, *, method="cash", note="", user=None):
    """دفعة للمورد على أمر مستلم. مينفعش المبلغ يزيد عن المتبقي، وكل دفعة ليها قيد (مدين الموردين، دائن النقدية)."""
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if method not in dict(PurchasePayment.METHODS):
        raise ValueError("طريقة الدفع غير صحيحة")
    if amount <= 0:
        raise ValueError("المبلغ لازم يكون أكبر من صفر")
    # قفل صف الأمر عشان دفعتين في نفس اللحظة ما يعدّوش المتبقي (على PostgreSQL)
    locked = PurchaseOrder.objects.select_for_update().get(pk=order.pk, company=order.company)
    if locked.status != "received":
        raise ValueError("الدفع بيتسجّل بعد استلام الأمر")
    if locked.billed_total <= 0:
        raise ValueError("الأمر مفيهوش مستحقات للمورد")
    if amount > locked.balance:
        raise ValueError(f"المبلغ أكبر من المتبقي للمورد ({locked.balance})")
    payment = PurchasePayment.objects.create(order=locked, amount=amount, method=method,
                                             note=(note or "")[:200], created_by=user)
    from accounting.services import post_supplier_payment
    post_supplier_payment(payment, user=user)
    return payment
