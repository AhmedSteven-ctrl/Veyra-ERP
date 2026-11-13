from django.contrib import admin

from .models import SalesLine, SalesOrder


class SalesLineInline(admin.TabularInline):
    model = SalesLine
    extra = 0


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "status", "company")
    list_filter = ("company", "status")
    inlines = [SalesLineInline]
