"""
Admin configuration for AdminInvitation model.
"""

import logging

from django.contrib import admin, messages
from django.utils import timezone
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from authn.models import AdminInvitation
from authn.services.email.invitation_mail import InvitationEmailError, send_admin_invitation_email

logger = logging.getLogger(__name__)


@admin.register(AdminInvitation)
class AdminInvitationAdmin(UnfoldModelAdmin):
    list_display = ["email", "role", "status_badge", "invited_by", "created_at", "expires_at"]
    list_filter = ["status", "role"]
    search_fields = ["email"]
    readonly_fields = [
        "token",
        "status",
        "invited_by",
        "accepted_by",
        "expires_at",
        "accepted_at",
        "created_at",
        "updated_at",
    ]
    actions = ["resend_invitation", "cancel_invitations"]

    # noinspection PyUnusedLocal
    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                (None, {"fields": ("email", "role", "message")}),
            ]
        return [
            (None, {"fields": ("email", "role", "status", "message")}),
            ("Details", {"fields": ("token", "invited_by", "accepted_by", "expires_at", "accepted_at")}),
            ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
        ]

    # noinspection PyUnusedLocal
    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return self.readonly_fields + ["email", "role", "message"]
        return self.readonly_fields

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            AdminInvitation.Status.PENDING: "#f59e0b",
            AdminInvitation.Status.ACCEPTED: "#10b981",
            AdminInvitation.Status.EXPIRED: "#6b7280",
            AdminInvitation.Status.CANCELLED: "#ef4444",
        }
        # Show expired badge for pending invitations that have expired
        status = obj.status
        if status == AdminInvitation.Status.PENDING and obj.is_expired:
            status = AdminInvitation.Status.EXPIRED
        color = colors.get(status, "#6b7280")
        label = AdminInvitation.Status(status).label if status != obj.status else obj.get_status_display()
        return f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#fff;background:{color};">{label}</span>'

    status_badge.allow_tags = True

    def save_model(self, request, obj, form, change):
        if not change:
            obj.token = AdminInvitation.generate_token()
            obj.invited_by = request.user
            obj.expires_at = AdminInvitation.default_expiry()

            # Cancel previous pending invitations for the same email
            AdminInvitation.objects.filter(
                email__iexact=obj.email,
                status=AdminInvitation.Status.PENDING,
            ).update(status=AdminInvitation.Status.CANCELLED, updated_at=timezone.now())

            super().save_model(request, obj, form, change)

            try:
                send_admin_invitation_email(obj, request)
                messages.success(request, f"Invitation sent to {obj.email}.")
            except InvitationEmailError as exc:
                logger.exception("Failed to send invitation email to %s", obj.email)
                messages.warning(request, f"Invitation created but email failed to send: {exc}")
        else:
            super().save_model(request, obj, form, change)

    @admin.action(description="Resend invitation email")
    def resend_invitation(self, request, queryset):
        sent = 0
        for invitation in queryset.filter(status=AdminInvitation.Status.PENDING):
            if invitation.is_expired:
                continue
            try:
                send_admin_invitation_email(invitation, request)
                sent += 1
            except InvitationEmailError as exc:
                messages.warning(request, f"Failed to resend to {invitation.email}: {exc}")
        if sent:
            messages.success(request, f"Resent {sent} invitation(s).")

    @admin.action(description="Cancel selected invitations")
    def cancel_invitations(self, request, queryset):
        count = queryset.filter(status=AdminInvitation.Status.PENDING).update(
            status=AdminInvitation.Status.CANCELLED,
            updated_at=timezone.now(),
        )
        messages.success(request, f"Cancelled {count} invitation(s).")
