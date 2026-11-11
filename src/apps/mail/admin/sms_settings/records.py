"""Read-only records of SMS links and ticket texts (Mail → SMS Links, Ticket SMS)."""

from django.contrib import admin, messages
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin
from apps.mail.models import SmsLinkToken, TicketSms
from apps.mail.services.sms.links import revoke_links


@admin.register(SmsLinkToken)
class SmsLinkTokenAdmin(ReadOnlyModelAdmin):
    # The token itself is never shown: only its digest is stored (a shared link keeps its plain token to put it in
    # every recipient's text, and is no credential, but it stays off this page too).
    list_display = (
        "purpose",
        "kind",
        "campaign",
        "registration",
        "member",
        "created_at",
        "expires_at",
        "first_used_at",
        "use_count",
        "status_badge",
    )
    list_filter = ("purpose", "campaign")
    list_select_related = ("campaign", "registration__event", "member")
    ordering = ("-created_at",)
    fields = (
        "purpose",
        "campaign",
        "registration",
        "member",
        "redirect_path",
        "created_at",
        "expires_at",
        "first_used_at",
        "use_count",
    )
    actions = ["revoke_selected_action"]

    @display(description="Kind")
    def kind(self, obj):
        return "Personal sign-in" if obj.is_personal else "Shared"

    @display(description="Status", label={"active": "success", "used": "info", "expired": "danger"})
    def status_badge(self, obj):
        if obj.is_expired:
            return "expired"
        if obj.is_personal and obj.first_used_at:
            return "used"
        return "active"

    @admin.action(description="Revoke selected SMS links", permissions=["revoke"])
    def revoke_selected_action(self, request, queryset):
        revoked = revoke_links(queryset)
        self.message_user(request, f"Revoked {revoked} SMS link(s).", messages.SUCCESS)

    def has_revoke_permission(self, request):
        return self._has_app_access(request)


@admin.register(TicketSms)
class TicketSmsAdmin(ReadOnlyModelAdmin):
    list_display = ("registration", "phone_number", "status_badge", "error_message", "attempts", "sent_at")
    list_filter = ("status",)
    search_fields = ("phone_number", "registration__ticket_code")
    list_select_related = ("registration__event",)
    ordering = ("-created_at",)
    fields = (
        "registration",
        "phone_number",
        "status",
        "error_message",
        "message_id",
        "available_at",
        "sent_at",
        "attempts",
        "created_at",
    )

    @display(
        description="Status",
        label={
            "Waiting to send": "info",
            "Sent": "success",
            "Failed": "danger",
            "Uncertain delivery": "warning",
            "Not sent": "info",
            "Opted out": "warning",
        },
    )
    def status_badge(self, obj):
        return obj.get_status_display()
