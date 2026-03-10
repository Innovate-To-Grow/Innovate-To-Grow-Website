"""
Read-only admin configuration for SES email audit logs.
"""

from django.contrib import admin
from django.utils.html import format_html

from core.admin.base import ReadOnlyModelAdmin
from mail.models import SESEmailLog


@admin.register(SESEmailLog)
class SESEmailLogAdmin(ReadOnlyModelAdmin):
    """Read-only admin for SES send logs."""

    list_display = (
        "action_badge",
        "subject_truncated",
        "recipients_truncated",
        "status_badge",
        "performed_by",
        "created_at",
    )
    list_filter = ("status", "account", "created_at")
    search_fields = ("subject", "recipients", "ses_message_id")
    date_hierarchy = "created_at"
    list_per_page = 50

    @admin.display(description="Action", ordering="action")
    def action_badge(self, obj):
        return format_html(
            '<span style="background:#28a745; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px;">{}</span>',
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
        color = "#28a745" if obj.status == SESEmailLog.Status.SUCCESS else "#dc3545"
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )
