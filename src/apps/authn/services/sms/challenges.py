"""The durable challenge behind each phone code being sent (the send itself is orchestrated in ``sns_verify``).

The code material, the per-number hourly cap and degradation, the reservation committed before the provider call,
and the challenge's state once the provider answered (sent, failed) or when nothing is sent at all (withheld).
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.email.challenges.degradation import FAILURE_WINDOW, max_attempts_for

from .errors import (
    ACTIVE_STATUSES,
    MAX_SENDS_PER_HOUR,
    MAX_VERIFY_ATTEMPTS,
    OTP_TTL_SECONDS,
    PhoneVerificationDeliveryError,
    PhoneVerificationThrottled,
)

# The historical logger name: these functions used to live in ``sns_verify``.
logger = logging.getLogger("apps.authn.services.sms.sns_verify")

TOO_MANY_ATTEMPTS = "Too many verification attempts. Please try again later."


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _unmatchable_code() -> str:
    """What a withheld challenge is hashed from: a secret that no 6-digit code can equal, so the challenge can never
    be approved, while checking a guess against it costs exactly what it costs against a real code."""
    return secrets.token_urlsafe(32)


def _mark_challenge_sent(challenge_id) -> bool:
    now = timezone.now()
    return bool(
        PhoneVerificationChallenge.objects.filter(
            pk=challenge_id,
            status=PhoneVerificationChallenge.Status.SENDING,
        ).update(
            status=PhoneVerificationChallenge.Status.PENDING,
            sent_at=now,
            updated_at=now,
        )
    )


def _mark_challenge_delivery_failed(challenge_id) -> None:
    try:
        PhoneVerificationChallenge.objects.filter(
            pk=challenge_id,
            status=PhoneVerificationChallenge.Status.SENDING,
        ).update(
            status=PhoneVerificationChallenge.Status.EXPIRED,
            updated_at=timezone.now(),
        )
    except Exception:  # noqa: BLE001 - the durable reservation must remain visible.
        logger.exception("Unable to record SMS delivery failure for challenge %s", challenge_id)


def _recent_phone_failures(phone_number: str, *, now) -> int:
    """Failed code guesses against ``phone_number`` (E.164) over the degradation window (see ``degradation``).

    One aggregate query answered by the ``(phone_number, send_reserved_at)`` index; ``send_reserved_at`` is the issue
    time of every challenge ``start_phone_verification`` creates. Only wrong guesses increment ``attempts``.
    """
    total = PhoneVerificationChallenge.objects.filter(
        phone_number=phone_number,
        send_reserved_at__gte=now - FAILURE_WINDOW,
    ).aggregate(total=Sum("attempts"))["total"]
    return int(total or 0)


def _recent_sends(phone_number: str, *, now) -> int:
    return PhoneVerificationChallenge.objects.filter(
        phone_number=phone_number,
        send_reserved_at__gte=now - timedelta(hours=1),
    ).count()


def _refuse_capped_number(phone_number: str, *, now) -> None:
    """A plain read of the per-number hourly cap, before the shared SMS slot is taken: requests for a capped number
    must not advance the pace other numbers' codes wait for. ``_reserve_challenge`` checks again under the lock."""
    if _recent_sends(phone_number, now=now) >= MAX_SENDS_PER_HOUR:
        raise PhoneVerificationThrottled(TOO_MANY_ATTEMPTS)


def _reserve_challenge(phone_number: str, *, purpose, member, context_identifier, code: str, now, spend_budget=True):
    """Commit the new challenge (expiring earlier ones) before the external provider call.

    A crash or database failure after delivery can no longer erase the hourly cap. ``spend_budget=False`` (a withheld
    code, which is never sent) refuses a spent SMS daily budget exactly as a send would, but takes no unit of it.
    """
    from apps.authn.services.send_verification.quotas import check_sms_dispatch, reserve_sms_dispatch

    try:
        with transaction.atomic():
            if _recent_sends(phone_number, now=now) >= MAX_SENDS_PER_HOUR:
                raise PhoneVerificationThrottled(TOO_MANY_ATTEMPTS)
            # A number with many recent failed guesses gets single-guess codes (per number, all purposes).
            max_attempts = max_attempts_for(_recent_phone_failures(phone_number, now=now), MAX_VERIFY_ATTEMPTS)
            PhoneVerificationChallenge.objects.select_for_update().filter(
                phone_number=phone_number,
                purpose=purpose,
                status__in=ACTIVE_STATUSES,
            ).update(
                status=PhoneVerificationChallenge.Status.EXPIRED,
                updated_at=now,
            )
            challenge = PhoneVerificationChallenge.objects.create(
                phone_number=phone_number,
                purpose=purpose,
                member=member,
                context_identifier=str(context_identifier or ""),
                code_hash=make_password(code),
                status=PhoneVerificationChallenge.Status.SENDING,
                max_attempts=max_attempts,
                expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
                send_reserved_at=now,
            )
            # One unit of the global SMS daily budget, taken last (so the shared budget row is locked only for
            # this UPDATE and the commit) and in the same transaction as the challenge row: a spent budget
            # raises ``SendThrottled`` and rolls the whole reservation back (no challenge, earlier codes stay
            # valid); otherwise the unit is committed before the provider call below and is never released.
            if spend_budget:
                reserve_sms_dispatch(destination=phone_number, now=now)
            else:
                check_sms_dispatch(destination=phone_number, now=now)
    except PhoneVerificationThrottled:
        raise
    except (IntegrityError, ValidationError, ValueError) as exc:
        raise PhoneVerificationThrottled("A verification code was already requested. Please try again.") from exc
    return challenge


def _finalize_sent_challenge(challenge) -> None:
    try:
        finalized = _mark_challenge_sent(challenge.pk)
    except Exception:  # noqa: BLE001 - provider already accepted the message.
        logger.exception("Unable to finalize delivered SMS challenge %s", challenge.pk)
        finalized = False
    if (
        not finalized
        and not PhoneVerificationChallenge.objects.filter(
            pk=challenge.pk,
            status=PhoneVerificationChallenge.Status.SENDING,
        ).exists()
    ):
        raise PhoneVerificationDeliveryError("SMS challenge could not be finalized.", challenge_id=str(challenge.pk))


def _withhold_otp(challenge) -> None:
    """Record a withheld challenge like a sent one (its id on the send request, pending) without sending anything.

    ``sent_at`` stays empty: that, and the log line, are what tell an operator that no SMS went out.
    """
    from apps.authn.services.send_verification.outcomes import record_otp_challenge

    record_otp_challenge(str(challenge.pk))
    PhoneVerificationChallenge.objects.filter(pk=challenge.pk, status=PhoneVerificationChallenge.Status.SENDING).update(
        status=PhoneVerificationChallenge.Status.PENDING, updated_at=timezone.now()
    )
