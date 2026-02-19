from django.contrib import admin
from unfold.admin import ModelAdmin

from ...models import GoogleSheet


@admin.register(GoogleSheet)
class GoogleSheetAdmin(ModelAdmin):
    list_display = ("name", "spreadsheet_id", "sheet_name", "is_enabled", "cache_ttl_seconds", "updated_at")
    list_filter = ("is_enabled",)
    list_editable = ("is_enabled",)
    search_fields = ("name", "spreadsheet_id", "sheet_name")
    ordering = ("name",)
