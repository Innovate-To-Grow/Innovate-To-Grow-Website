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
        "error_preview",
        "provider",
        "sent_at",
    )
    list_filter = ("status", "provider", "campaign")
    search_fields = ("email_address", "recipient_name")
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
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"pending": "info", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="Error")
    def error_preview(self, obj):
        if not obj.error_message:
            return "-"
        return obj.error_message[:120] + "..." if len(obj.error_message) > 120 else obj.error_message
