from django.contrib import admin
from unfold.admin import ModelAdmin

from ...models import GoogleSheetSource


@admin.register(GoogleSheetSource)
class GoogleSheetSourceAdmin(ModelAdmin):
    list_display = ("slug", "title", "sheet_type", "is_active", "created_at")
    list_filter = ("sheet_type", "is_active")
    search_fields = ("slug", "title")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("slug", "title", "sheet_type", "is_active")}),
        ("Spreadsheet", {"fields": ("spreadsheet_id", "range_a1")}),
        ("Tracks", {"fields": ("tracks_spreadsheet_id", "tracks_sheet_name"), "classes": ("collapse",)}),
        ("Filtering & Cache", {"fields": ("semester_filter", "cache_ttl_seconds")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
