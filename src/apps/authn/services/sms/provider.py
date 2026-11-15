"""The SMS provider boundary of phone verification (the send itself is orchestrated in ``sns_verify``).

AWS configuration, the OTP message, the delivery-rate slot (taken and given back) and the send through
``core.services.aws.sms_send``, with each provider failure mapped to its phone-verification error.
"""

from __future__ import annotations

import logging

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_PERMANENT
from apps.core.services.aws.sms_errors import SmsOptedOut
from apps.core.services.aws.sms_opt_outs import refuse_if_opted_out
from apps.core.services.aws.sms_send import (
    SmsDeliveryError,
    SmsRateDeferred,
    admit_text,
    resolve_sender,
    send_text_message,
)
from apps.core.services.delivery_rates import Lane, release

from .errors import (
    PhoneNumberOptedOut,
    PhoneVerificationBusy,
    PhoneVerificationDeliveryError,
    PhoneVerificationError,
    PhoneVerificationInvalid,
)

# The historical logger name: these functions used to live in ``sns_verify``.
logger = logging.getLogger("apps.authn.services.sms.sns_verify")


def _load_aws_config():
    from apps.core.models import AWSCredentialConfig

    return AWSCredentialConfig.load()


def _assert_configured():
    """Ensure AWS SMS settings are ready."""
    aws = _load_aws_config()
    if not aws.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.", outcome=PROVIDER_OUTCOME_PERMANENT)
    return aws


def _verification_error(exc: SmsDeliveryError) -> PhoneVerificationError:
    """The OTP error for a failed SMS send: held back (by the limiter or AWS) is ``PhoneVerificationBusy``, a number
    that opted out ``PhoneNumberOptedOut``."""
    if isinstance(exc, SmsOptedOut):
        return PhoneNumberOptedOut()
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


def _refuse_opted_out_number(phone_number: str) -> None:
    """A number on the SMS opt-out list is refused before it takes the shared SMS slot, the hourly cap or a unit of
    the daily budget (the send itself checks again)."""
    try:
        refuse_if_opted_out(phone_number)
    except SmsDeliveryError as exc:
        raise _verification_error(exc) from exc


def _render_otp_message(aws_config, code: str) -> str:
    # Rendered before anything is reserved: a broken template costs neither an hourly slot nor an SMS budget unit.
    try:
        return aws_config.render_sms_otp_message(code)
    except ValueError as exc:
        raise PhoneVerificationDeliveryError(
            "SMS message template is invalid.",
            outcome=PROVIDER_OUTCOME_PERMANENT,
        ) from exc
