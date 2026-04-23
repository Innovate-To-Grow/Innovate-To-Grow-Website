from django.contrib import admin
from unfold.decorators import display

from core.admin import ReadOnlyModelAdmin

from ..models import RecipientLog


@admin.register(RecipientLog)
class RecipientLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "campaign",
        "recipient_name",
        "email_address",
        "status_badge",
        "bounce_badge",
        "error_preview",
        "provider",
        "sent_at",
        "last_event_at",
    )
    list_filter = ("status", "bounce_type", "provider", "campaign")
    search_fields = ("email_address", "recipient_name", "ses_message_id")
    ordering = ("-updated_at",)

    fieldsets = (
        (
            None,
            {"fields": ("campaign", "member", "email_address", "recipient_name")},
        ),
        (
            "Delivery",
            {"fields": ("status", "provider", "error_message", "sent_at")},
        ),
        (
            "SES tracking",
            {
                "fields": (
                    "ses_message_id",
                    "delivered_at",
                    "bounced_at",
                    "complained_at",
                    "bounce_type",
                    "bounce_subtype",
                    "diagnostic_code",
                    "complaint_feedback_type",
                    "last_event_type",
                    "last_event_at",
                    "last_sns_message_id",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {
            "pending": "info",
            "sent": "info",
            "delivered": "success",
            "bounced": "danger",
            "complained": "warning",
            "rejected": "danger",
            "failed": "danger",
        }
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="Bounce", label=True)
    def bounce_badge(self, obj):
        if not obj.bounce_type:
            return "—", "info"
        color = "danger" if obj.bounce_type == "Permanent" else "warning"
        subtype = f"/{obj.bounce_subtype}" if obj.bounce_subtype else ""
        return f"{obj.bounce_type}{subtype}", color

    @display(description="Error")
    def error_preview(self, obj):
        # Pick the most informative text per terminal state. For bounces the
        # SMTP diagnostic from the recipient's MX server is far more useful
        # than the bounce type alone, which is already its own column.
        text = obj.error_message
        if not text and obj.status == "bounced":
            text = obj.diagnostic_code or obj.bounce_subtype
        elif not text and obj.status == "complained":
            text = obj.complaint_feedback_type or "complaint"
        if not text:
            return "-"
        return text[:120] + "..." if len(text) > 120 else text
