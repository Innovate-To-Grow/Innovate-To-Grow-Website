"""
AWS SMS service for phone number verification.

OTP codes are generated locally, stored in PostgreSQL, and delivered through AWS
End User Messaging (``pinpoint-sms-voice-v2`` SendTextMessage, sent by
``core.services.aws.sms_send`` under the delivery-rate limiter). Dedicated
origination numbers (toll-free/10DLC) are managed by End User Messaging, so the
legacy ``sns:Publish`` path cannot use them — it rejects the number with
"does not belong to the account". AWS credentials, region, and the origination
identity all live on AWSCredentialConfig.

This module orchestrates the send. Its collaborators live beside it (the provider boundary in ``provider``, the
durable challenge in ``challenges``, the per-number lock in ``phone_lock``) and are called through this module's
names, so tests replace them here (``sns_verify._publish_sms``, ``sns_verify._random_code``, ...).
"""

from __future__ import annotations

import logging
import time

from django.utils import timezone

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_UNCERTAIN
from apps.core.services.delivery_rates import Lane

from . import latency
from .challenges import (
    _finalize_sent_challenge,
    _mark_challenge_delivery_failed,
    _random_code,
    _refuse_capped_number,
    _reserve_challenge,
    _unmatchable_code,
    _withhold_otp,
)
from .checks import _check_phone_verification, check_phone_verification
from .errors import (
    ACTIVE_STATUSES,
    DEFAULT_PURPOSE,
    DEFAULT_STATUS,
    MAX_SENDS_PER_HOUR,
    MAX_VERIFY_ATTEMPTS,
    OTP_TTL_SECONDS,
    VERIFIABLE_STATUSES,
    VERIFIED_GRANT_TTL_SECONDS,
    PhoneNumberOptedOut,
    PhoneVerificationBusy,
    PhoneVerificationDeliveryError,
    PhoneVerificationError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)
from .phone_lock import _lock_phone
from .provider import (
    _admit_otp,
    _assert_configured,
    _load_aws_config,
    _publish_sms,
    _refuse_opted_out_number,
    _release_unsent,
    _render_otp_message,
)
from .verified_grants import consume_verified_phone_challenge

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
    "PhoneNumberOptedOut",
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

    A number on the SMS opt-out list is refused first (``PhoneNumberOptedOut``), and one already at its hourly cap
    next, with a plain read, so neither takes the shared SMS slot.
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
    _refuse_opted_out_number(phone_number)
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
