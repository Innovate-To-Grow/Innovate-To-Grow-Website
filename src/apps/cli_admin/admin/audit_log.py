from django.contrib import admin
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin

from ..models import CliAuditLog


@admin.register(CliAuditLog)
class CliAuditLogAdmin(ReadOnlyModelAdmin):
    """Read-only audit trail of CLI write operations."""

    list_display = (
        "created_at",
        "actor",
        "action_badge",
        "status_badge",
        "app_label",
        "model_name",
        "target_repr",
        "error_short",
    )
    list_filter = ("action", "status", "app_label")
    list_select_related = ("actor",)
    search_fields = ("app_label", "model_name", "target_pk", "target_repr")
    ordering = ("-created_at",)

    @display(description="Action", label=True)
    def action_badge(self, obj):
        colors = {"create": "success", "update": "info", "delete": "danger"}
        return obj.get_action_display(), colors.get(obj.action, "info")

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"success": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @admin.display(description="Error")
    def error_short(self, obj):
        if not obj.error_message:
            return "—"
        return obj.error_message[:80]
