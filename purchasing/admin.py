from django.contrib import admin

from .models import PurchaseLine, PurchaseOrder, PurchasePayment


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


class PurchasePaymentInline(admin.TabularInline):
    """الدفعات للقراءة بس: بتتسجّل من شاشة الأمر عشان كل دفعة ليها قيد محاسبي."""
    model = PurchasePayment
    extra = 0
    fields = ("amount", "method", "note", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "status", "billed_total", "company")
    list_filter = ("company", "status")
    search_fields = ("number", "supplier__name")
    readonly_fields = ("billed_total",)
    inlines = [PurchaseLineInline, PurchasePaymentInline]


@admin.register(PurchasePayment)
class PurchasePaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "method", "created_at")
    list_filter = ("method",)
    readonly_fields = ("order", "amount", "method", "note", "created_by")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
