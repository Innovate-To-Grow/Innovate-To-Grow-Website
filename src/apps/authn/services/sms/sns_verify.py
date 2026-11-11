"""
AWS SMS service for phone number verification.

OTP codes are generated locally, stored in PostgreSQL, and delivered through AWS
End User Messaging (``pinpoint-sms-voice-v2`` SendTextMessage, sent by
``core.services.aws.sms_send`` under the delivery-rate limiter). Dedicated
origination numbers (toll-free/10DLC) are managed by End User Messaging, so the
legacy ``sns:Publish`` path cannot use them — it rejects the number with
"does not belong to the account". AWS credentials, region, and the origination
identity all live on AWSCredentialConfig.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.email.challenges.degradation import FAILURE_WINDOW, max_attempts_for
from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_PERMANENT, PROVIDER_OUTCOME_UNCERTAIN
from apps.core.services.aws.sms_send import (
    SmsDeliveryError,
    SmsRateDeferred,
    admit_text,
    resolve_sender,
    send_text_message,
)
from apps.core.services.delivery_rates import Lane, release

from . import latency
from .checks import (
    _check_phone_verification,
    check_phone_verification,
    consume_verified_phone_challenge,
)
from .errors import (
    ACTIVE_STATUSES,
    DEFAULT_PURPOSE,
    DEFAULT_STATUS,
    MAX_SENDS_PER_HOUR,
    MAX_VERIFY_ATTEMPTS,
    OTP_TTL_SECONDS,
    VERIFIABLE_STATUSES,
    VERIFIED_GRANT_TTL_SECONDS,
    PhoneVerificationBusy,
    PhoneVerificationDeliveryError,
    PhoneVerificationError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)

logger = logging.getLogger(__name__)

# Code checking and the shared errors/limits moved to ``checks`` / ``errors``; they stay importable here.
__all__ = [
    "ACTIVE_STATUSES",
    "DEFAULT_PURPOSE",
    "DEFAULT_STATUS",
    "MAX_SENDS_PER_HOUR",
    "MAX_VERIFY_ATTEMPTS",
    "OTP_TTL_SECONDS",
    "VERIFIABLE_STATUSES",
    "VERIFIED_GRANT_TTL_SECONDS",
    "PhoneVerificationBusy",
    "PhoneVerificationDeliveryError",
    "PhoneVerificationError",
    "PhoneVerificationInvalid",
    "PhoneVerificationThrottled",
    "_check_phone_verification",
    "check_phone_verification",
    "consume_verified_phone_challenge",
    "publish_plain_sms",
    "start_phone_verification",
]

_LOCAL_PHONE_LOCKS = tuple(threading.Lock() for _ in range(64))
TOO_MANY_ATTEMPTS = "Too many verification attempts. Please try again later."


def _load_aws_config():
    from apps.core.models import AWSCredentialConfig

    return AWSCredentialConfig.load()


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _unmatchable_code() -> str:
    """What a withheld challenge is hashed from: a secret that no 6-digit code can equal, so the challenge can never
    be approved, while checking a guess against it costs exactly what it costs against a real code."""
    return secrets.token_urlsafe(32)


def _assert_configured():
    """Ensure AWS SMS settings are ready."""
    aws = _load_aws_config()
    if not aws.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.", outcome=PROVIDER_OUTCOME_PERMANENT)
    return aws


def _verification_error(exc: SmsDeliveryError) -> PhoneVerificationError:
    """The OTP error for a failed SMS send: held back (by the limiter or AWS) is ``PhoneVerificationBusy``."""
    if isinstance(exc, SmsRateDeferred) or exc.held_back:
        return PhoneVerificationBusy(exc.retry_after)
    if exc.code == "ValidationException":
        return PhoneVerificationInvalid("Invalid phone number.")
    # ConflictException / ResourceNotFoundException / AccessDeniedException point at the
    # origination identity or account state, not a bad recipient — surface as delivery errors.
    return PhoneVerificationDeliveryError(str(exc), outcome=exc.outcome)


def _publish_sms(*, phone_number: str, message: str, aws_config, admission=None, lane: str = Lane.TRANSACTIONAL) -> str:
    """Send one SMS through the delivery-rate limiter (``core.services.aws.sms_send``) on ``lane``, using
    ``admission`` when the caller already took the slot."""
    try:
        sender = resolve_sender(aws_config)
        return send_text_message(phone_number, message, lane=lane, sender=sender, admission=admission)
    except SmsDeliveryError as exc:
        raise _verification_error(exc) from exc


def _admit_otp(aws_config, message: str):
    """Take the OTP's SMS slot, waiting for it up to the inline wait; ``PhoneVerificationBusy`` when held back."""
    try:
        return admit_text(resolve_sender(aws_config), message, lane=Lane.TRANSACTIONAL)
    except SmsDeliveryError as exc:
        raise _verification_error(exc) from exc


def _release_unsent(admission) -> None:
    """Give back the slot of an OTP that never reached AWS (a no-op once the send recorded AWS's answer)."""
    try:
        release(admission)
    except Exception:  # noqa: BLE001 - the OTP's own outcome must reach the caller unchanged.
        logger.exception("Could not release the delivery-rate slot of an unsent OTP")


def _phone_lock_id(phone_number: str) -> int:
    digest = hashlib.sha256(phone_number.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


@contextmanager
def _lock_phone(phone_number: str):
    """Serialize one phone across reservation, provider call, and finalization."""
    lock_id = _phone_lock_id(phone_number)
    local_lock = _LOCAL_PHONE_LOCKS[abs(lock_id) % len(_LOCAL_PHONE_LOCKS)]
    with local_lock:
        if connection.vendor != "postgresql":
            yield
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])


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


def _render_otp_message(aws_config, code: str) -> str:
    # Rendered before anything is reserved: a broken template costs neither an hourly slot nor an SMS budget unit.
    try:
        return aws_config.render_sms_otp_message(code)
    except ValueError as exc:
        raise PhoneVerificationDeliveryError(
            "SMS message template is invalid.",
            outcome=PROVIDER_OUTCOME_PERMANENT,
        ) from exc


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


def _deliver_otp(challenge, *, phone_number: str, message: str, aws_config, admission) -> str:
    from apps.authn.services.send_verification.outcomes import record_otp_challenge

    try:
        record_otp_challenge(str(challenge.pk))
        started = time.monotonic()
        message_id = _publish_sms(
            phone_number=phone_number, message=message, aws_config=aws_config, admission=admission
        )
        # How long a delivered code took, so a withheld one can take as long (``latency``).
        latency.observe_send(time.monotonic() - started)
        return message_id
    except Exception as exc:
        # An uncertain provider call may have delivered this OTP. Keep it
        # verifiable and retain both durable reservations.
        if isinstance(exc, PhoneVerificationInvalid | PhoneVerificationThrottled) or (
            getattr(exc, "outcome", PROVIDER_OUTCOME_UNCERTAIN) != PROVIDER_OUTCOME_UNCERTAIN
        ):
            _mark_challenge_delivery_failed(challenge.pk)
        if isinstance(exc, PhoneVerificationDeliveryError):
            exc.challenge_id = str(challenge.pk)
        raise


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


def start_phone_verification(
    phone_number: str,
    *,
    purpose: str = DEFAULT_PURPOSE,
    member=None,
    context_identifier: str = "",
    deliver: bool = True,
) -> dict[str, str]:
    """
    Generate and durably store an OTP, then send it via AWS End User Messaging.

    This is the only place an OTP SMS leaves the system, so it is also where the global SMS daily budget is spent:
    one unit per provider call, reserved together with the challenge row and never released (an uncertain or failed
    provider call keeps it). Raises ``SendThrottled`` (from ``send_verification``) when the budget is spent; nothing
    is stored or sent in that case.

    A number already at its hourly cap is refused first, with a plain read, so it never takes the shared SMS slot.
    The slot is taken next, before the number is locked or anything is reserved: an SMS delivery held back raises
    ``PhoneVerificationBusy`` and spends neither the hourly cap nor the daily budget. A refusal after that (the cap
    reached meanwhile, the budget) gives the slot back.

    ``deliver=False`` issues a *withheld* challenge (phone sign-in for a number saved on an account but not verified):
    every refusal above applies in the same order, and the challenge is reserved and counted exactly as for a send,
    but its code is never sent and never matches (hashed from ``_unmatchable_code``). No provider call, no unit of the
    SMS daily budget (a spent one is still refused, ``check_sms_dispatch``), the delivery slot is given back, and the
    answer comes after about as long as a real provider call takes (``latency``).

    Returns ``{"status": "pending", "challenge_id": "..."}``.
    """
    aws_config = _assert_configured()
    code = _random_code()
    message = _render_otp_message(aws_config, code)
    _refuse_capped_number(phone_number, now=timezone.now())
    admission = _admit_otp(aws_config, message)
    try:
        now = timezone.now()
        with _lock_phone(phone_number):
            challenge = _reserve_challenge(
                phone_number,
                purpose=purpose,
                member=member,
                context_identifier=context_identifier,
                code=code if deliver else _unmatchable_code(),
                now=now,
                spend_budget=deliver,
            )
            if deliver:
                message_id = _deliver_otp(
                    challenge, phone_number=phone_number, message=message, aws_config=aws_config, admission=admission
                )
                _finalize_sent_challenge(challenge)
            else:
                _withhold_otp(challenge)
    finally:
        _release_unsent(admission)

    if deliver:
        logger.info("Phone verification started: message_id=%s", message_id)
    else:
        latency.wait_like_a_send()
        logger.info("Phone verification withheld, nothing sent: challenge=%s", challenge.pk)
    return {"status": DEFAULT_STATUS, "challenge_id": str(challenge.pk)}


def publish_plain_sms(*, phone_number: str, message: str, lane: str = Lane.TRANSACTIONAL) -> str:
    """Send a plain SMS message via AWS End User Messaging on ``lane``: the admin test SMS is transactional, the
    in-process SMS campaign passes ``Lane.BULK``. Held back raises ``PhoneVerificationBusy``."""
    aws_config = _load_aws_config()
    if not aws_config.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.")
    return _publish_sms(phone_number=phone_number, message=message, aws_config=aws_config, lane=lane)
