"""
Twilio Verify SMS service for phone number verification.

Credentials are loaded from the SMSServiceConfig singleton in the database.
"""

import logging

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

logger = logging.getLogger(__name__)


class PhoneVerificationError(RuntimeError):
    """Base exception for phone verification failures."""


class PhoneVerificationThrottled(PhoneVerificationError):
    """Too many verification attempts."""


class PhoneVerificationInvalid(PhoneVerificationError):
    """Invalid or expired verification code."""


class PhoneVerificationDeliveryError(PhoneVerificationError):
    """Failed to send SMS."""


def _load_config():
    from core.models import SMSServiceConfig

    return SMSServiceConfig.load()


def _get_client_and_sid() -> tuple[Client, str]:
    config = _load_config()
    if not config.is_configured:
        raise PhoneVerificationDeliveryError("Twilio is not configured.")
    return Client(config.account_sid, config.auth_token), config.verify_sid


def start_phone_verification(phone_number: str) -> str:
    """
    Start a phone verification via Twilio Verify.
    Returns the verification status (usually 'pending').
    """
    client, verify_sid = _get_client_and_sid()
    try:
        verification = client.verify.v2.services(verify_sid).verifications.create(to=phone_number, channel="sms")
        logger.info(
            "Phone verification started: status=%s",
            verification.status,
        )
        return verification.status
    except TwilioRestException as exc:
        logger.warning("Twilio verification start failed")
        if exc.code == 60203:
            raise PhoneVerificationThrottled("Too many verification attempts. Please try again later.") from exc
        if exc.code in (60200, 21211, 21608):
            raise PhoneVerificationInvalid("Invalid phone number.") from exc
        raise PhoneVerificationDeliveryError("Failed to send verification SMS.") from exc


def check_phone_verification(phone_number: str, code: str) -> str:
    """
    Check a verification code against Twilio Verify.
    Returns the verification status ('approved' on success).
    """
    client, verify_sid = _get_client_and_sid()
    try:
        check = client.verify.v2.services(verify_sid).verification_checks.create(to=phone_number, code=code)
        if check.status == "approved":
            logger.info("Phone verification approved")
            return check.status
        raise PhoneVerificationInvalid("Verification code is invalid or has expired.")
    except TwilioRestException as exc:
        logger.warning("Twilio verification check failed")
        if exc.code == 60202:
            raise PhoneVerificationThrottled("Too many failed attempts. Please request a new code.") from exc
        raise PhoneVerificationInvalid("Verification code is invalid or has expired.") from exc
