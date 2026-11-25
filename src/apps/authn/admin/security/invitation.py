"""
Admin configuration for AdminInvitation model.
"""

import logging
from functools import partial

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html

from apps.authn.models import AdminInvitation
from apps.core.admin import BaseModelAdmin
from apps.core.services.delivery_rates import Family, inline_batch_limit

logger = logging.getLogger("apps.authn.admin.members.invitation")  # its log name before the move


@admin.register(AdminInvitation)
class AdminInvitationAdmin(BaseModelAdmin):
    """Admin invitations: any Admin may invite, and accepting an invitation creates an Admin account.

    The invitation link is a bearer secret that creates an Admin, so its change page shows it only to the Admin who
    sent it (to copy when the email fails); an invitation stops working once its sender is no longer an Admin.
    """

    list_display = ["email", "role", "status_badge", "invited_by", "created_at", "expires_at"]
    list_filter = ["status", "role"]
    search_fields = ["email"]
    readonly_fields = [
        "invitation_link",
        "status",
        "invited_by",
        "accepted_by",
        "expires_at",
        "accepted_at",
        "created_at",
        "updated_at",
    ]
    actions = ["resend_invitations", "cancel_invitations"]

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                (None, {"fields": ("email", "role", "message")}),
            ]
        detail_fields = ("invitation_link", "invited_by", "accepted_by", "expires_at", "accepted_at")
        return [
            (None, {"fields": ("email", "role", "status", "message")}),
            ("Details", {"fields": detail_fields}),
            ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
        ]

    # noinspection PyUnusedLocal
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for field in ("email", "role", "message"):
                if field not in readonly:
                    readonly.append(field)
        return readonly

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        if obj is not None:
            obj._viewing_request = request  # per request: the admin instance is shared between requests
        return obj

    @admin.display(description="Invitation link")
    def invitation_link(self, obj):
        request = getattr(obj, "_viewing_request", None)
        if request is None:
            return "-"
        if obj.invited_by_id != request.user.pk:
            return "Shown only to the Admin who sent it."
        if not obj.is_valid:
            return "No longer valid."
        return obj.get_acceptance_url(request)

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
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#fff;background:{};">{}</span>',
            color,
            label,
        )

    def save_model(self, request, obj, form, change):
        obj.email = (obj.email or "").strip().lower()
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
            # The admin saves inside a transaction; the email (paced, and possibly waiting for its slot) goes after
            # the commit, so no lock is held across the provider call. Its message still reaches the response.
            transaction.on_commit(partial(self._send_invitation_message, request, obj, created=True), robust=True)
        else:
            super().save_model(request, obj, form, change)

    def _send_invitation_message(self, request, invitation, *, created=False, show_success=True):
        from apps.authn.services.email import send_admin_invitation_email

        try:
            send_admin_invitation_email(invitation=invitation, request=request)
        except Exception:
            logger.exception("Failed to send admin invitation email for %s", invitation.email)
            created_text = "created, but " if created else ""
            if invitation.invited_by_id == request.user.pk:
                fallback = f"Copy the invitation link manually: {invitation.get_acceptance_url(request)}"
            else:
                fallback = "Its link is shown only to the Admin who sent it."
            messages.error(
                request, f"Invitation {created_text}email could not be sent to {invitation.email}. {fallback}"
            )
            return False

        if show_success:
            verb = "created and sent" if created else "resent"
            messages.success(request, f"Invitation {verb} for {invitation.email}.")
        return True

    @admin.action(description="Resend selected pending invitations")
    def resend_invitations(self, request, queryset):
        # The emails wait for their delivery slots inside this request, so it takes only as many as the email
        # channel's current rate sends in one request's budget.
        limit = inline_batch_limit(Family.EMAIL)
        if limit is not None and queryset.count() > limit:
            messages.error(
                request,
                f"{queryset.count()} invitations cannot be resent from one request at the current email send rate "
                f"(limit {limit}; see Mail → Delivery Rates). Select fewer invitations.",
            )
            return
        sent = 0
        skipped = 0

        for invitation in queryset:
            if not invitation.is_valid:
                if invitation.status == AdminInvitation.Status.PENDING and invitation.is_expired:
                    invitation.mark_expired()
                skipped += 1
                continue

            if self._send_invitation_message(request, invitation, show_success=False):
                sent += 1

        if skipped:
            messages.warning(request, f"Skipped {skipped} invalid, expired, or already-used invitation(s).")
        if sent:
            messages.success(request, f"Resent {sent} invitation email(s).")

    @admin.action(description="Cancel selected invitations")
    def cancel_invitations(self, request, queryset):
        count = queryset.filter(status=AdminInvitation.Status.PENDING).update(
            status=AdminInvitation.Status.CANCELLED,
            updated_at=timezone.now(),
        )
        messages.success(request, f"Cancelled {count} invitation(s).")
