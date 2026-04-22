from django.contrib import admin
from unfold.decorators import display

from core.admin import ReadOnlyModelAdmin

from ..models import ScheduleSyncLog


@admin.register(ScheduleSyncLog)
class ScheduleSyncLogAdmin(ReadOnlyModelAdmin):
    list_display = ("config", "sync_type_badge", "status_badge", "sections_created", "tracks_created", "slots_created", "error_short", "created_at")
    list_filter = ("sync_type", "status")
    ordering = ("-created_at",)

    @display(description="Type", label=True)
    def sync_type_badge(self, obj):
        if obj.sync_type == ScheduleSyncLog.SyncType.AUTO:
            return "Auto", "info"
        return "Manual", "warning"

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.status == ScheduleSyncLog.Status.SUCCESS:
            return "Success", "success"
        return "Failed", "danger"

    @admin.display(description="Error")
    def error_short(self, obj):
        if not obj.error_message:
            return "-"
        return obj.error_message[:80] + "..." if len(obj.error_message) > 80 else obj.error_message
