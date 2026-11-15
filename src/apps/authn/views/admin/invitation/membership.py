"""Who an accepted invitation makes staff: a new member, or the verified member who already owns the address."""

from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from apps.authn.models import ContactEmail
from apps.authn.models.members.admin_invitation import AdminInvitation


class InvitationEmailConflict(Exception):
    """The invited address is already owned by a different member."""


Member = None  # resolved lazily


def _get_member_model():
    global Member
    if Member is None:
        from django.contrib.auth import get_user_model

        Member = get_user_model()
    return Member


class InvitationMembershipMixin:
    """The member-side steps of ``AcceptInvitationView``: find the invitation, create or upgrade the member."""

    def _create_member(self, form, invitation):
        with transaction.atomic():
            # noinspection PyPep8Naming
            MemberModel = _get_member_model()
            member = MemberModel(
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                organization=form.cleaned_data.get("organization", ""),
                is_staff=True,
                is_active=True,
            )
            password = form.cleaned_data["password1"]
            validate_password(password, user=member)
            member.set_password(password)
            member.save()

            self._attach_invitation_email(member, invitation)
            invitation.mark_accepted(member)
        self._created_member = member

    def _get_invitation(self, token):
        # The token comes from the URL. PostgreSQL rejects a NUL in a string parameter, and nothing longer than
        # the column can match, so such values are "invalid" without a query (and without a 500).
        if "\x00" in token or len(token) > AdminInvitation._meta.get_field("token").max_length:
            return None
        try:
            invitation = AdminInvitation.objects.get(token=token)
        except AdminInvitation.DoesNotExist:
            return None

        if not invitation.is_valid:
            if invitation.status == AdminInvitation.Status.PENDING and invitation.is_expired:
                invitation.mark_expired()
            return None

        return invitation

    def _get_verified_member(self, invitation):
        contact = (
            ContactEmail.objects.filter(
                email_address__iexact=invitation.email,
                verified=True,
                member__isnull=False,
            )
            .select_related("member")
            .first()
        )
        return contact.member if contact else None

    def _attach_invitation_email(self, member, invitation):
        contact = ContactEmail.objects.select_for_update().filter(email_address__iexact=invitation.email).first()
        if contact is None:
            ContactEmail.objects.create(
                member=member,
                email_address=invitation.email,
                email_type="primary",
                verified=True,
                subscribe=True,
            )
            return

        if contact.member_id is not None and contact.member_id != member.pk:
            # Re-pointing a ContactEmail that another member already owns is an account-takeover
            # primitive (it moves a sign-in address between accounts) — the same thing the CLI
            # denylist exists to prevent. Refuse instead.
            raise InvitationEmailConflict(
                "That email address already belongs to another member. Ask an I2G Master to resolve it."
            )

        contact.member = member
        contact.email_type = "primary"
        contact.verified = True
        contact.save(update_fields=["member", "email_type", "verified", "updated_at"])

    def _upgrade_member(self, member, invitation):
        # Upgrade the member and mark the invitation accepted atomically so a
        # failure between the two writes can't leave a staff-upgraded member with
        # a still-PENDING invitation.
        with transaction.atomic():
            member.is_staff = True
            member.is_active = True
            member.save(update_fields=["is_staff", "is_active", "updated_at"])
            invitation.mark_accepted(member)
