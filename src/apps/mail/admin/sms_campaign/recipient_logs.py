"""Per-recipient SMS delivery logs: the campaign inline and their own read-only admin."""

from django.contrib import admin
from unfold.admin import TabularInline
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin
from apps.core.utils.access import user_can_access_app
from apps.mail.models import SmsRecipientLog


class SmsRecipientLogInline(TabularInline):
    model = SmsRecipientLog
    fields = ("phone_number", "recipient_name", "status", "error_message", "provider", "sent_at")
    readonly_fields = fields
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SmsRecipientLog)
class SmsRecipientLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "campaign",
        "recipient_name",
        "phone_number",
        "status_badge",
        "error_preview",
        "provider",
        "sent_at",
    )
    list_filter = ("status", "provider", "campaign")
    search_fields = ("phone_number", "recipient_name", "sns_message_id")
    list_select_related = ("campaign",)
    ordering = ("-updated_at",)

    fieldsets = (
        (None, {"fields": ("campaign", "member", "phone_number", "recipient_name")}),
        ("Delivery", {"fields": ("status", "provider", "error_message", "sns_message_id", "sent_at")}),
    )

    def has_delete_permission(self, request, obj=None):
        return user_can_access_app(request.user, "mail")

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"pending": "info", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="Error")
    def error_preview(self, obj):
        if not obj.error_message:
            return "-"
        return obj.error_message[:120] + "..." if len(obj.error_message) > 120 else obj.error_message
