"""
AWS SMS service for phone number verification.

OTP codes are generated locally, stored in PostgreSQL, and delivered through AWS
End User Messaging (``pinpoint-sms-voice-v2`` SendTextMessage). Dedicated
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
from contextlib import contextmanager
from datetime import timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.email.challenges.degradation import FAILURE_WINDOW, max_attempts_for
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.core.services.aws.provider_outcomes import (
    NO_PROVIDER_RETRIES,
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_UNCERTAIN,
    classify_aws_send_failure,
)

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


def _load_aws_config():
    from apps.core.models import AWSCredentialConfig

    return AWSCredentialConfig.load()


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _assert_configured():
    """Ensure AWS SMS settings are ready."""
    aws = _load_aws_config()
    if not aws.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.", outcome=PROVIDER_OUTCOME_PERMANENT)
    return aws


def _get_smsvoice_client():
    try:
        creds = resolve_aws_credentials("sns")
    except AwsCredentialsError as exc:
        raise PhoneVerificationDeliveryError(
            "AWS credentials are not configured.",
            outcome=PROVIDER_OUTCOME_PERMANENT,
        ) from exc

    return boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=creds.region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
        config=NO_PROVIDER_RETRIES,
    )


def _publish_sms(*, phone_number: str, message: str, aws_config) -> str:
    origination_identity = aws_config.resolved_sms_from_number()
    if not origination_identity:
        raise PhoneVerificationDeliveryError("SMS is not configured.", outcome=PROVIDER_OUTCOME_PERMANENT)

    client = _get_smsvoice_client()
    try:
        response = client.send_text_message(
            DestinationPhoneNumber=phone_number,
            OriginationIdentity=origination_identity,
            MessageBody=message,
            MessageType="TRANSACTIONAL",
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        logger.warning("send_text_message failed: code=%s", error_code)
        if error_code in {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}:
            raise PhoneVerificationThrottled("Too many verification attempts. Please try again later.") from exc
        if error_code == "ValidationException":
            raise PhoneVerificationInvalid("Invalid phone number.") from exc
        # ConflictException / ResourceNotFoundException / AccessDeniedException point at the
        # origination identity or account state, not a bad recipient — surface as delivery errors.
        outcome, message = classify_aws_send_failure(exc, provider="SMS")
        raise PhoneVerificationDeliveryError(message, outcome=outcome) from exc
    except BotoCoreError as exc:
        logger.warning("send_text_message failed", exc_info=True)
        outcome, message = classify_aws_send_failure(exc, provider="SMS")
        raise PhoneVerificationDeliveryError(message, outcome=outcome) from exc

    return response.get("MessageId", "")


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


def _render_otp_message(aws_config, code: str) -> str:
    # Rendered before anything is reserved: a broken template costs neither an hourly slot nor an SMS budget unit.
    try:
        return aws_config.render_sms_otp_message(code)
    except ValueError as exc:
        raise PhoneVerificationDeliveryError(
            "SMS message template is invalid.",
            outcome=PROVIDER_OUTCOME_PERMANENT,
        ) from exc


def _reserve_challenge(phone_number: str, *, purpose, member, context_identifier, code: str, now):
    """Commit the new challenge (expiring earlier ones) before the external provider call.

    A crash or database failure after delivery can no longer erase the hourly cap.
    """
    from apps.authn.services.send_verification.quotas import reserve_sms_dispatch

    try:
        with transaction.atomic():
            recent_sends = PhoneVerificationChallenge.objects.filter(
                phone_number=phone_number,
                send_reserved_at__gte=now - timedelta(hours=1),
            ).count()
            if recent_sends >= MAX_SENDS_PER_HOUR:
                raise PhoneVerificationThrottled("Too many verification attempts. Please try again later.")
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
            reserve_sms_dispatch(destination=phone_number, now=now)
    except PhoneVerificationThrottled:
        raise
    except (IntegrityError, ValidationError, ValueError) as exc:
        raise PhoneVerificationThrottled("A verification code was already requested. Please try again.") from exc
    return challenge


def _deliver_otp(challenge, *, phone_number: str, message: str, aws_config) -> str:
    from apps.authn.services.send_verification.outcomes import record_otp_challenge

    try:
        record_otp_challenge(str(challenge.pk))
        return _publish_sms(phone_number=phone_number, message=message, aws_config=aws_config)
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


def start_phone_verification(
    phone_number: str,
    *,
    purpose: str = DEFAULT_PURPOSE,
    member=None,
    context_identifier: str = "",
) -> dict[str, str]:
    """
    Generate and durably store an OTP, then send it via AWS End User Messaging.

    This is the only place an OTP SMS leaves the system, so it is also where the global SMS daily budget is spent:
    one unit per provider call, reserved together with the challenge row and never released (an uncertain or failed
    provider call keeps it). Raises ``SendThrottled`` (from ``send_verification``) when the budget is spent; nothing
    is stored or sent in that case.

    Returns ``{"status": "pending", "challenge_id": "..."}``.
    """
    aws_config = _assert_configured()
    code = _random_code()
    message = _render_otp_message(aws_config, code)
    now = timezone.now()
    with _lock_phone(phone_number):
        challenge = _reserve_challenge(
            phone_number, purpose=purpose, member=member, context_identifier=context_identifier, code=code, now=now
        )
        message_id = _deliver_otp(challenge, phone_number=phone_number, message=message, aws_config=aws_config)
        _finalize_sent_challenge(challenge)

    logger.info("Phone verification started: message_id=%s", message_id)
    return {"status": DEFAULT_STATUS, "challenge_id": str(challenge.pk)}


def publish_plain_sms(*, phone_number: str, message: str) -> str:
    """Send a plain SMS message via AWS End User Messaging (used by admin test-send)."""
    aws_config = _load_aws_config()
    if not aws_config.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.")
    return _publish_sms(phone_number=phone_number, message=message, aws_config=aws_config)
