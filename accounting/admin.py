from django.contrib import admin

from .models import Account, AccountMapping, Journal, JournalEntry, JournalLine


class LineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "nature", "is_group", "is_active", "parent", "company")
    list_filter = ("company", "type", "kind", "is_group", "is_active")
    search_fields = ("code", "name")


@admin.register(AccountMapping)
class AccountMappingAdmin(admin.ModelAdmin):
    list_display = ("company", "role", "account")
    list_filter = ("company", "role")


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company")


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("reference", "journal", "memo", "company")
    inlines = [LineInline]
