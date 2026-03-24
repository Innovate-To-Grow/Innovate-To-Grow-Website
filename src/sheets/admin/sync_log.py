from django.contrib import admin
from unfold.admin import ModelAdmin

from sheets.models import SyncLog


@admin.register(SyncLog)
class SyncLogAdmin(ModelAdmin):
    list_display = (
        "sheet_link",
        "direction",
        "status",
        "rows_processed",
        "rows_created",
        "rows_updated",
        "rows_failed",
        "started_at",
        "completed_at",
    )
    list_filter = ("direction", "status")
    search_fields = ("sheet_link__name",)
    readonly_fields = (
        "id",
        "sheet_link",
        "direction",
        "status",
        "rows_processed",
        "rows_created",
        "rows_updated",
        "rows_skipped",
        "rows_failed",
        "error_details",
        "started_at",
        "completed_at",
        "triggered_by",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (None, {"fields": ("sheet_link", "direction", "status", "triggered_by")}),
        (
            "Stats",
            {
                "fields": (
                    "rows_processed",
                    "rows_created",
                    "rows_updated",
                    "rows_skipped",
                    "rows_failed",
                ),
            },
        ),
        ("Errors", {"fields": ("error_details",), "classes": ("collapse",)}),
        ("Timing", {"fields": ("started_at", "completed_at")}),
        ("Metadata", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
