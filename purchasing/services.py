from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from inventory.services import StockError, receive, update_average_cost

from .models import PurchaseAgreement, PurchaseOrder, PurchasePayment, SupplierPrice


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


# ============================== قوائم أسعار المورد ==============================
def best_supplier_price(company, supplier_id, product, qty, on=None):
    """أفضل سعر مورد لصنف بكمية معينة في يوم معين: أعلى شريحة كمية مناسبة (min_qty <= qty)،
    ولو شريحتين بنفس الكمية يبقى الأرخص. بيرجع None لو مفيش سعر ساري."""
    on = on or date.today()
    qs = (SupplierPrice.objects.filter(company=company, supplier_id=supplier_id, product=product, min_qty__lte=qty)
          .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=on))
          .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on))
          .order_by("-min_qty", "price"))
    row = qs.first()
    return row.price if row else None


# ============================== اتفاقيات الشراء ==============================
def _claim_agreement(agreement, *, from_status, to_status):
    statuses = (from_status,) if isinstance(from_status, str) else tuple(from_status)
    return PurchaseAgreement.objects.filter(pk=agreement.pk, company=agreement.company, status__in=statuses)\
        .update(status=to_status, updated_at=timezone.now())


def _agreement_why_not(agreement, action):
    agreement.refresh_from_db(fields=["status"])
    status = agreement.status
    if status == "cancelled":
        return "الاتفاقية ملغية"
    if status == "closed":
        return "الاتفاقية مغلقة"
    if status == "active" and action == "activate":
        return "الاتفاقية سارية بالفعل"
    if status == "draft" and action == "close":
        return "لازم تفعّل الاتفاقية الأول"
    return "الإجراء ده مش متاح على الاتفاقية في حالتها الحالية"


@transaction.atomic
def activate_agreement(agreement: PurchaseAgreement):
    """تفعيل المسودة (لازم فيها أصناف)."""
    if not agreement.lines.exists():
        raise ValueError("الاتفاقية مفيهاش أصناف")
    if not _claim_agreement(agreement, from_status="draft", to_status="active"):
        raise ValueError(_agreement_why_not(agreement, "activate"))
    agreement.status = "active"
    return agreement


@transaction.atomic
def close_agreement(agreement: PurchaseAgreement):
    """إغلاق اتفاقية سارية (خلصت أو اتنفذت)."""
    if not _claim_agreement(agreement, from_status="active", to_status="closed"):
        raise ValueError(_agreement_why_not(agreement, "close"))
    agreement.status = "closed"
    return agreement


@transaction.atomic
def cancel_agreement(agreement: PurchaseAgreement):
    """إلغاء اتفاقية مسودة أو سارية. الطلبات اللي اتعملت منها قبل كده بتفضل زي ما هي."""
    if not _claim_agreement(agreement, from_status=("draft", "active"), to_status="cancelled"):
        raise ValueError(_agreement_why_not(agreement, "cancel"))
    agreement.status = "cancelled"
    return agreement


def agreement_order_lines(agreement: PurchaseAgreement, today=None):
    """سطور طلب الشراء اللي هيتعمل من الاتفاقية: [(الصنف، الكمية المتبقية، السعر المتفق عليه)].
    الاتفاقية لازم تكون سارية وفي فترتها، ولازم يكون فيه كمية متبقية."""
    today = today or date.today()
    agreement.refresh_from_db(fields=["status"])
    if agreement.status != "active":
        raise ValueError("الاتفاقية مش سارية")
    if agreement.start_date and agreement.start_date > today:
        raise ValueError("الاتفاقية لسه ما بدأتش")
    if agreement.end_date and agreement.end_date < today:
        raise ValueError("الاتفاقية انتهت")
    lines = [(l.product, l.remaining, l.price) for l in agreement.lines.select_related("product")]
    lines = [row for row in lines if row[1] > 0]
    if not lines:
        raise ValueError("كل كميات الاتفاقية اتطلبت")
    return lines
