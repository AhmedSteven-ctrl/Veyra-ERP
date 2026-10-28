from django.db import transaction
from inventory.services import issue, receive
from .models import SalesOrder, SalesReturn


@transaction.atomic
def convert_quote_to_order(order: SalesOrder):
    """تحويل عرض السعر إلى أمر بيع مؤكد"""
    if order.status != "quote":
        raise ValueError("الأمر ليس عرض سعر لإنهاء تحويله")
    order.status = "confirmed"
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def deliver(order: SalesOrder, warehouse, user=None):
    """التسليم: يصرف كل أصناف الأمر من المخزن في معاملة واحدة وترحيل قيد المبيعات."""
    if order.status in ["delivered", "returned"]:
        raise ValueError("الأمر اتسلّم أو تم إرجاعه قبل كده")
    for line in order.lines.select_related("product"):
        issue(company=order.company, product=line.product, warehouse=warehouse,
              qty=line.qty, reference=order.number, user=user)
    order.status = "delivered"
    order.save(update_fields=["status", "updated_at"])
    from accounting.services import post_sale
    post_sale(order, user=user)
    return order


@transaction.atomic
def process_return(order: SalesOrder, warehouse, reason="", user=None):
    """مرتجع المبيعات: إرجاع البضاعة للمخزن وعكس القيد المحاسبي."""
    if order.status != "delivered":
        raise ValueError("يمكن إرجاع الطلبات المسلمة فقط")
    
    return_num = f"RET-{order.number}"
    sales_return = SalesReturn.objects.create(
        company=order.company,
        number=return_num,
        order=order,
        reason=reason
    )
    
    # إرجاع الكميات للمخزن
    for line in order.lines.select_related("product"):
        receive(company=order.company, product=line.product, warehouse=warehouse,
                qty=line.qty, reference=return_num, user=user)
                
    order.status = "returned"
    order.save(update_fields=["status", "updated_at"])
    
    # القيد المحاسبي المكتبي للمرتجع
    from accounting.services import post_sale_return
    post_sale_return(order, return_num, user=user)
    
    return sales_return
