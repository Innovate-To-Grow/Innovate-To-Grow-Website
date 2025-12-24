from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from ..models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """
    Enhanced admin for notification logs with detailed management.
    """

    list_display = (
        "id",
        "channel_badge",
        "target",
        "subject_preview",
        "provider",
        "status_badge",
        "sent_at",
        "created_at",
    )
    list_filter = ("channel", "status", "provider", "created_at", "sent_at")
    search_fields = ("target", "subject", "message", "error_message")
    readonly_fields = (
        "created_at",
        "updated_at",
        "sent_at",
        "message_preview",
        "error_preview",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    list_select_related = True
    save_on_top = True

    fieldsets = (
        (
            "Delivery Info",
            {
                "fields": ("channel", "target", "provider"),
                "description": "Channel and recipient details.",
            },
        ),
        (
            "Message Content",
            {
                "fields": ("subject", "message", "message_preview"),
            },
        ),
        (
            "Delivery Status",
            {
                "fields": ("status", "error_message", "error_preview"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("sent_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_as_sent", "mark_as_failed", "retry_send"]

    @admin.display(description="Channel")
    def channel_badge(self, obj):
        colors = {"email": "#3498db", "sms": "#27ae60"}
        color = colors.get(obj.channel, "#7f8c8d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_channel_display(),
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "pending": "#f39c12",
            "sent": "#27ae60",
            "failed": "#e74c3c",
        }
        color = colors.get(obj.status, "#7f8c8d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Subject")
    def subject_preview(self, obj):
        if not obj.subject:
            return format_html('<span style="color:#95a5a6;">—</span>')
        if len(obj.subject) > 40:
            return obj.subject[:40] + "..."
        return obj.subject

    @admin.display(description="Message Preview")
    def message_preview(self, obj):
        if not obj.message:
            return "—"
        preview = obj.message[:200] + "..." if len(obj.message) > 200 else obj.message
        return format_html('<pre style="white-space:pre-wrap;">{}</pre>', preview)

    @admin.display(description="Error Preview")
    def error_preview(self, obj):
        if not obj.error_message:
            return format_html('<span style="color:#27ae60;">No errors</span>')
        return format_html(
            '<pre style="white-space:pre-wrap; color:#e74c3c;">{}</pre>',
            obj.error_message[:500],
        )

    @admin.action(description="Mark selected as sent")
    def mark_as_sent(self, request, queryset):
        updated = queryset.update(status=NotificationLog.STATUS_SENT, sent_at=timezone.now())
        self.message_user(request, f"{updated} notification(s) marked as sent.")

    @admin.action(description="Mark selected as failed")
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status=NotificationLog.STATUS_FAILED)
        self.message_user(request, f"{updated} notification(s) marked as failed.")

    @admin.action(description="Retry sending selected notifications")
    def retry_send(self, request, queryset):
        from ..services import send_notification

        count = 0
        for log in queryset.filter(status=NotificationLog.STATUS_FAILED):
            send_notification(
                channel=log.channel,
                target=log.target,
                message=log.message,
                subject=log.subject,
                provider=log.provider if log.provider != "console" else None,
            )
            count += 1
        self.message_user(request, f"Retried sending {count} notification(s).")

