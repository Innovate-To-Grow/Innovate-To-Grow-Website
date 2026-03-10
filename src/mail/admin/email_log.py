"""
Admin configuration for EmailLog (read-only audit log).
"""

from django.contrib import admin
from django.utils.html import format_html

from core.admin.base import ReadOnlyModelAdmin
from mail.models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(ReadOnlyModelAdmin):
    """Read-only admin for email operation audit logs."""

    list_display = (
        "action_badge",
        "subject_truncated",
        "recipients_truncated",
        "status_badge",
        "performed_by",
        "created_at",
    )
    list_filter = ("action", "status", "account", "created_at")
    search_fields = ("subject", "recipients", "gmail_message_id")
    date_hierarchy = "created_at"
    list_per_page = 50

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description="Action", ordering="action")
    def action_badge(self, obj):
        colors = {
            "send": "#28a745",
            "reply": "#17a2b8",
            "forward": "#6f42c1",
            "read": "#6c757d",
            "delete": "#dc3545",
            "label": "#fd7e14",
        }
        color = colors.get(obj.action, "#6c757d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_action_display(),
        )

    @admin.display(description="Subject", ordering="subject")
    def subject_truncated(self, obj):
        if len(obj.subject) > 60:
            return f"{obj.subject[:60]}..."
        return obj.subject or "(no subject)"

    @admin.display(description="Recipients")
    def recipients_truncated(self, obj):
        if len(obj.recipients) > 50:
            return f"{obj.recipients[:50]}..."
        return obj.recipients or "-"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        if obj.status == EmailLog.Status.SUCCESS:
            return format_html(
                '<span style="color:#28a745; font-weight:bold;">{}</span>',
                obj.get_status_display(),
            )
        return format_html(
            '<span style="color:#dc3545; font-weight:bold;">{}</span>',
            obj.get_status_display(),
        )
