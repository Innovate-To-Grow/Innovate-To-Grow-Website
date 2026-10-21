"""Checking phone verification codes and consuming verified grants (sending lives in ``sns_verify``)."""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge

from .errors import (
    DEFAULT_PURPOSE,
    MAX_VERIFY_ATTEMPTS,
    VERIFIABLE_STATUSES,
    VERIFIED_GRANT_TTL_SECONDS,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)

# The historical logger name: these functions used to live in ``sns_verify``.
logger = logging.getLogger("apps.authn.services.sms.sns_verify")


def check_phone_verification(
    phone_number: str | None,
    code: str,
    *,
    challenge_id=None,
    purpose: str = DEFAULT_PURPOSE,
    member=None,
    context_identifier: str | None = None,
    consume: bool = True,
    approved_callback=None,
):
    """
    Check and atomically consume a durable verification challenge.

    ``challenge_id`` is the preferred API. For one compatibility release callers
    may omit it and the latest pending challenge for ``phone_number`` is used.
    """
    # Keep the successful state transition and any caller-supplied completion
    # work in one transaction. Auth callers use this hook to create/resolve the
    # member and mint refresh tokens before the OTP consumption can commit.
    # Invalid outcomes leave the block normally so attempt/expiry mutations
    # commit before the public exception is raised.
    callback_result = None
    with transaction.atomic():
        challenge, outcome = _check_phone_verification(
            phone_number=phone_number,
            code=code,
            challenge_id=challenge_id,
            purpose=purpose,
            member=member,
            context_identifier=context_identifier,
            consume=consume,
        )
        if challenge is not None and approved_callback is not None:
            callback_result = approved_callback(challenge)
    if outcome == "throttled":
        raise PhoneVerificationThrottled("Too many failed attempts. Please request a new code.")
    if challenge is None:
        raise PhoneVerificationInvalid("Verification code is invalid or has expired.")
    logger.info("Phone verification approved")
    return callback_result if approved_callback is not None else challenge


def _spent_code_outcome(challenge: PhoneVerificationChallenge) -> str:
    """The outcome for a wrong guess that uses up (or finds used up) ``challenge``'s attempts.

    A normal code keeps the verifier's ``"throttled"`` answer on its last allowed guess. A degraded code (issued
    with fewer than ``MAX_VERIFY_ATTEMPTS`` guesses, see ``degradation``) is spent by its first wrong guess and
    answers ``"invalid"``, exactly what a first wrong guess gets on any other number, so no verify endpoint shows
    that a number is degraded.
    """
    return "throttled" if challenge.max_attempts >= MAX_VERIFY_ATTEMPTS else "invalid"


@transaction.atomic
def _check_phone_verification(
    *,
    phone_number: str | None,
    code: str,
    challenge_id,
    purpose: str,
    member,
    context_identifier: str | None,
    consume: bool,
) -> tuple[PhoneVerificationChallenge | None, str]:
    queryset = _candidate_challenges(
        phone_number=phone_number,
        challenge_id=challenge_id,
        purpose=purpose,
        member=member,
        context_identifier=context_identifier,
    )
    challenge = queryset.first() if queryset is not None else None
    if challenge is None:
        return None, "invalid"

    now = timezone.now()
    if challenge.expires_at <= now or challenge.attempts >= challenge.max_attempts:
        challenge.status = PhoneVerificationChallenge.Status.EXPIRED
        challenge.save(update_fields=["status", "updated_at"])
        return None, _spent_code_outcome(challenge) if challenge.attempts >= challenge.max_attempts else "invalid"

    if not check_password(code, challenge.code_hash):
        return None, _record_wrong_guess(challenge)
    if not _grant(challenge, consume=consume, now=now):
        return None, "invalid"
    return challenge, "approved"


def _candidate_challenges(*, phone_number, challenge_id, purpose, member, context_identifier):
    """Locked verifiable challenges for the input, or None when the input names none (or a malformed id)."""
    queryset = PhoneVerificationChallenge.objects.select_for_update().filter(
        purpose=purpose,
        status__in=VERIFIABLE_STATUSES,
    )
    if member is not None:
        queryset = queryset.filter(member=member)
    if context_identifier is not None:
        queryset = queryset.filter(context_identifier=str(context_identifier))
    if challenge_id:
        try:
            parsed_challenge_id = UUID(str(challenge_id))
        except (ValidationError, ValueError, TypeError):
            return None
        queryset = queryset.filter(pk=parsed_challenge_id)
        return queryset.filter(phone_number=phone_number) if phone_number else queryset
    if phone_number:
        return queryset.filter(phone_number=phone_number).order_by("-created_at")
    return None


def _record_wrong_guess(challenge: PhoneVerificationChallenge) -> str:
    challenge.attempts += 1
    if challenge.attempts >= challenge.max_attempts:
        challenge.status = PhoneVerificationChallenge.Status.EXPIRED
    challenge.save(update_fields=["attempts", "status", "updated_at"])
    spent = challenge.status == PhoneVerificationChallenge.Status.EXPIRED
    return _spent_code_outcome(challenge) if spent else "invalid"


def _grant(challenge: PhoneVerificationChallenge, *, consume: bool, now) -> bool:
    """Move a correct code to consumed (or to a verified grant); False when another request won the race."""
    next_status = PhoneVerificationChallenge.Status.CONSUMED if consume else PhoneVerificationChallenge.Status.VERIFIED
    update_fields = {"status": next_status, "updated_at": now}
    if consume:
        update_fields["consumed_at"] = now
    else:
        update_fields["verified_at"] = now
        update_fields["expires_at"] = now + timedelta(seconds=VERIFIED_GRANT_TTL_SECONDS)
    updated = PhoneVerificationChallenge.objects.filter(
        pk=challenge.pk,
        status__in=VERIFIABLE_STATUSES,
        expires_at__gt=now,
    ).update(**update_fields)
    if not updated:
        return False
    challenge.status = next_status
    if consume:
        challenge.consumed_at = now
    else:
        challenge.verified_at = now
        challenge.expires_at = update_fields["expires_at"]
    return True


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
