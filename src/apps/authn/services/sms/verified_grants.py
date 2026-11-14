"""Consuming a verified phone grant: the second step after ``check_phone_verification(..., consume=False)``."""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge

from .errors import PhoneVerificationInvalid


@transaction.atomic
def consume_verified_phone_challenge(
    *,
    phone_number: str,
    purpose: str,
    member,
    context_identifier: str,
    challenge_id=None,
    compatibility_context_identifiers: tuple[str, ...] = (),
) -> PhoneVerificationChallenge:
    """Consume a verified grant inside the caller's database transaction.

    Event registration uses this two-step form so code verification and form
    submission can be separate HTTP requests without falling back to cache.
    ``challenge_id`` may be omitted for one compatibility release.
    """
    allowed_contexts = (
        str(context_identifier),
        *(str(value) for value in compatibility_context_identifiers),
    )
    queryset = PhoneVerificationChallenge.objects.select_for_update().filter(
        phone_number=phone_number,
        purpose=purpose,
        member=member,
        context_identifier__in=allowed_contexts,
        status=PhoneVerificationChallenge.Status.VERIFIED,
    )
    if challenge_id:
        try:
            parsed_challenge_id = UUID(str(challenge_id))
        except (ValidationError, ValueError, TypeError) as exc:
            raise PhoneVerificationInvalid("Verification proof is invalid or has expired.") from exc
        queryset = queryset.filter(pk=parsed_challenge_id)
    else:
        queryset = queryset.order_by("-verified_at", "-created_at")

    challenge = queryset.first()
    now = timezone.now()
    if challenge is None or challenge.expires_at <= now:
        if challenge is not None:
            challenge.status = PhoneVerificationChallenge.Status.EXPIRED
            challenge.save(update_fields=["status", "updated_at"])
        raise PhoneVerificationInvalid("Verification proof is invalid or has expired.")

    updated = PhoneVerificationChallenge.objects.filter(
        pk=challenge.pk,
        status=PhoneVerificationChallenge.Status.VERIFIED,
        expires_at__gt=now,
    ).update(
        status=PhoneVerificationChallenge.Status.CONSUMED,
        consumed_at=now,
        updated_at=now,
    )
    if not updated:
        raise PhoneVerificationInvalid("Verification proof is invalid or has expired.")
    challenge.status = PhoneVerificationChallenge.Status.CONSUMED
    challenge.consumed_at = now
    return challenge
