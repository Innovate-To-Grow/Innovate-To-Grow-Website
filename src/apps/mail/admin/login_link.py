"""Read-only admin for emailed login-link tokens, with revocation."""

from django.contrib import admin, messages
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin

from ..models import LoginLinkToken
from ..services.login_links import revoke_login_links


@admin.register(LoginLinkToken)
class LoginLinkTokenAdmin(ReadOnlyModelAdmin):
    list_display = (
        "member",
        "campaign",
        "registration",
        "created_at",
        "expires_at",
        "used_at",
        "status_badge",
    )
    list_filter = ("is_used", "campaign")
    search_fields = ("member__contact_emails__email_address",)
    # registration__event: status_badge reads is_reusable, which follows
    # registration.event for ticket-issued tokens.
    list_select_related = ("member", "campaign", "registration__event")
    ordering = ("-created_at",)

    # The raw token is the secret behind the emailed link — never expose it.
    fields = (
        "member",
        "campaign",
        "registration",
        "redirect_path",
        "created_at",
        "expires_at",
        "used_at",
        "is_used",
    )

    actions = ["revoke_selected_action"]

    @display(
        description="Status",
        label={"active": "success", "reusable": "success", "used": "info", "expired": "danger"},
    )
    def status_badge(self, obj):
        if obj.is_expired:
            return "expired"
        # A reusable link stays live after use — don't render it like a
        # consumed one-time token, or operators may skip revoking it.
        if obj.is_reusable:
            return "reusable"
        if obj.is_used:
            return "used"
        return "active"

    @admin.action(description="Revoke selected login links", permissions=["revoke"])
    def revoke_selected_action(self, request, queryset):
        revoked = revoke_login_links(queryset)
        self.message_user(request, f"Revoked {revoked} login link(s).", messages.SUCCESS)

    def has_revoke_permission(self, request):
        return request.user.has_perm("mail.change_loginlinktoken")
