"""
AWS SNS SMS service for phone number verification.

OTP codes are generated locally, stored in cache, and delivered via SNS publish.
AWS credentials are resolved from AWSCredentialConfig or EmailServiceConfig SES keys.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache

from core.services.aws.credentials import AwsCredentialsError, aws_credentials_available, resolve_aws_credentials

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 600
MAX_VERIFY_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 10
DEFAULT_STATUS = "pending"


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


def _phone_digest(phone_number: str) -> str:
    return hashlib.sha256(phone_number.encode("utf-8")).hexdigest()


def _otp_cache_key(phone_number: str) -> str:
    return f"sms:otp:{_phone_digest(phone_number)}"


def _send_count_cache_key(phone_number: str) -> str:
    return f"sms:send-count:{_phone_digest(phone_number)}"


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _assert_configured():
    config = _load_config()
    if not config.is_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.")
    return config


def _get_sns_client(*, region: str):
    try:
        creds = resolve_aws_credentials()
    except AwsCredentialsError as exc:
        raise PhoneVerificationDeliveryError("AWS credentials are not configured.") from exc

    return boto3.client(
        "sns",
        region_name=region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
    )


def _publish_sms(*, phone_number: str, message: str, config) -> str:
    region = config.effective_region
    if not region:
        raise PhoneVerificationDeliveryError("SNS region is not configured.")

    client = _get_sns_client(region=region)
    message_attributes = {
        "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
    }
    if config.from_number:
        message_attributes["AWS.MM.SMS.OriginationNumber"] = {
            "DataType": "String",
            "StringValue": config.from_number,
        }

    try:
        response = client.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes=message_attributes,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        logger.warning("SNS publish failed: code=%s", error_code)
        if error_code in {"Throttling", "ThrottlingException", "TooManyRequestsException"}:
            raise PhoneVerificationThrottled("Too many verification attempts. Please try again later.") from exc
        if error_code in {"InvalidParameter", "InvalidParameterException", "OptedOut"}:
            raise PhoneVerificationInvalid("Invalid phone number.") from exc
        raise PhoneVerificationDeliveryError("Failed to send verification SMS.") from exc
    except BotoCoreError as exc:
        logger.warning("SNS publish failed", exc_info=True)
        raise PhoneVerificationDeliveryError("Failed to send verification SMS.") from exc

    return response.get("MessageId", "")


def _assert_send_allowed(phone_number: str) -> None:
    send_key = _send_count_cache_key(phone_number)
    send_count = cache.get(send_key, 0)
    if send_count >= MAX_SENDS_PER_HOUR:
        raise PhoneVerificationThrottled("Too many verification attempts. Please try again later.")


def _record_send(phone_number: str) -> None:
    send_key = _send_count_cache_key(phone_number)
    send_count = cache.get(send_key, 0) + 1
    cache.set(send_key, send_count, timeout=3600)


def start_phone_verification(phone_number: str) -> str:
    """
    Generate an OTP, store it in cache, and send it via AWS SNS.
    Returns the verification status (``pending``).
    """
    config = _assert_configured()
    _assert_send_allowed(phone_number)

    code = _random_code()
    cache.set(
        _otp_cache_key(phone_number),
        {"code_hash": make_password(code), "attempts": 0},
        timeout=OTP_TTL_SECONDS,
    )

    try:
        message = config.render_otp_message(code)
    except ValueError as exc:
        cache.delete(_otp_cache_key(phone_number))
        raise PhoneVerificationDeliveryError("SMS message template is invalid.") from exc

    message_id = _publish_sms(phone_number=phone_number, message=message, config=config)
    _record_send(phone_number)
    logger.info("Phone verification started via SNS: message_id=%s", message_id)
    return DEFAULT_STATUS


def check_phone_verification(phone_number: str, code: str) -> str:
    """
    Check a verification code against the cached OTP.
    Returns ``approved`` on success.
    """
    _assert_configured()

    cache_key = _otp_cache_key(phone_number)
    payload = cache.get(cache_key)
    if not payload:
        raise PhoneVerificationInvalid("Verification code is invalid or has expired.")

    attempts = payload.get("attempts", 0)
    if attempts >= MAX_VERIFY_ATTEMPTS:
        cache.delete(cache_key)
        raise PhoneVerificationThrottled("Too many failed attempts. Please request a new code.")

    if not check_password(code, payload["code_hash"]):
        attempts += 1
        if attempts >= MAX_VERIFY_ATTEMPTS:
            cache.delete(cache_key)
            raise PhoneVerificationThrottled("Too many failed attempts. Please request a new code.")
        cache.set(cache_key, {**payload, "attempts": attempts}, timeout=OTP_TTL_SECONDS)
        raise PhoneVerificationInvalid("Verification code is invalid or has expired.")

    cache.delete(cache_key)
    logger.info("Phone verification approved")
    return "approved"


def publish_plain_sms(*, phone_number: str, message: str, config=None) -> str:
    """Send a plain SMS message via SNS (used by admin test-send)."""
    config = config or _assert_configured()
    if not config.from_number:
        raise PhoneVerificationDeliveryError("Origination phone number is not configured.")
    if not aws_credentials_available():
        raise PhoneVerificationDeliveryError("AWS credentials are not configured.")
    return _publish_sms(phone_number=phone_number, message=message, config=config)
