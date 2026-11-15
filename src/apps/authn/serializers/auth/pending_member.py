"""The inactive member a registration starts with: created for the address, or the pending one that already owns it."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import serializers

from apps.authn.services import (
    claim_unclaimed_contact_email,
    get_pending_registration_member,
)

Member = get_user_model()


class PendingMemberMixin:
    """``_create_pending_member`` for ``RegisterSerializer``: the claim on the address can race another registration."""

    def _create_pending_member(self, email, password, first_name, last_name) -> Member:
        """Create an inactive member owning ``email``, or reuse the pending registration that already does.

        Claiming the address can race another registration for it; the loser deletes its new row and
        continues with the winner's pending member (or refuses when the address belongs to an account).
        """
        from apps.authn.models import ContactEmail

        member = Member.objects.create_user(
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,
            registration_pending=True,
        )
        if claim_unclaimed_contact_email(email, member=member) is not None:
            return member
        pending_member = get_pending_registration_member(email)
        if pending_member is not None:
            member.delete()
            return pending_member
        try:
            ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=False)
        except IntegrityError as exc:
            pending_member = get_pending_registration_member(email)
            member.delete()
            if pending_member is None:
                raise serializers.ValidationError({"email": "Unable to register with this email address."}) from exc
            return pending_member
        return member
