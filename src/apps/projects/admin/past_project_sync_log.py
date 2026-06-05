from django.contrib import admin

from apps.core.admin import ReadOnlyModelAdmin

from ..models import PastProjectSyncLog


@admin.register(PastProjectSyncLog)
class PastProjectSyncLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "created_at",
        "config",
        "sync_type",
        "status",
        "projects_created",
        "semesters_touched",
        "rows_skipped",
        "rows_read",
    )
    list_filter = ("status", "sync_type", "config")
    search_fields = ("error_message",)
    readonly_fields = (
        "config",
        "sync_type",
        "status",
        "rows_read",
        "projects_created",
        "semesters_touched",
        "rows_skipped",
        "error_message",
        "created_at",
        "updated_at",
    )
