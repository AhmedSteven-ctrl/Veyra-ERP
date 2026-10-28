from django.contrib import admin

from .models import PurchaseLine, PurchaseOrder


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "status", "company")
    list_filter = ("company", "status")
    inlines = [PurchaseLineInline]
