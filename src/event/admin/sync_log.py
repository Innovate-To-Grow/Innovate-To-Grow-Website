from django.contrib import admin
from unfold.decorators import display

from core.admin import ReadOnlyModelAdmin

from ..models import RegistrationSheetSyncLog


@admin.register(RegistrationSheetSyncLog)
class RegistrationSheetSyncLogAdmin(ReadOnlyModelAdmin):
    list_display = ("event", "sync_type_badge", "status_badge", "rows_written", "error_short", "created_at")
    list_filter = ("event", "sync_type", "status")
    search_fields = ("event__name", "error_message")
    ordering = ("-created_at",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    @display(description="Type", label=True)
    def sync_type_badge(self, obj):
        if obj.sync_type == RegistrationSheetSyncLog.SyncType.FULL:
            return "Full Sync", "warning"
        return "Append", "info"

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.status == RegistrationSheetSyncLog.Status.SUCCESS:
            return "Success", "success"
        return "Failed", "danger"

    @admin.display(description="Error")
    def error_short(self, obj):
        if not obj.error_message:
            return "-"
        return obj.error_message[:80] + "..." if len(obj.error_message) > 80 else obj.error_message
