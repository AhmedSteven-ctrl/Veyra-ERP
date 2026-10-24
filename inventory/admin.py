from django.contrib import admin

from .models import Product, StockMove, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "company")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "company", "sale_price")
    list_filter = ("company",)


@admin.register(StockMove)
class StockMoveAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "qty", "kind", "reference", "created_at")
    list_filter = ("company", "kind")
    readonly_fields = [f.name for f in StockMove._meta.fields]
