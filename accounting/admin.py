from django.contrib import admin

from .models import Account, Journal, JournalEntry, JournalLine


class LineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "type", "company")
    list_filter = ("company", "type")


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company")


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("reference", "journal", "memo", "company")
    inlines = [LineInline]
