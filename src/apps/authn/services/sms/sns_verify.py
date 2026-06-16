"""
AWS SMS service for phone number verification.

OTP codes are generated locally, stored in cache, and delivered through AWS
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

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache

from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

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


def _load_aws_config():
    from apps.core.models import AWSCredentialConfig

    return AWSCredentialConfig.load()


def _phone_digest(phone_number: str) -> str:
    return hashlib.sha256(phone_number.encode("utf-8")).hexdigest()


def _otp_cache_key(phone_number: str) -> str:
    return f"sms:otp:{_phone_digest(phone_number)}"


def _send_count_cache_key(phone_number: str) -> str:
    return f"sms:send-count:{_phone_digest(phone_number)}"


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _assert_configured():
    """Ensure AWS SMS settings are ready."""
    aws = _load_aws_config()
    if not aws.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.")
    return aws


def _get_smsvoice_client():
    try:
        creds = resolve_aws_credentials("sns")
    except AwsCredentialsError as exc:
        raise PhoneVerificationDeliveryError("AWS credentials are not configured.") from exc

    return boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=creds.region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
    )


def _publish_sms(*, phone_number: str, message: str, aws_config) -> str:
    origination_identity = aws_config.resolved_sms_from_number()
    if not origination_identity:
        raise PhoneVerificationDeliveryError("SMS is not configured.")

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
        if error_code in {"ValidationException", "ConflictException"}:
            raise PhoneVerificationInvalid("Invalid phone number.") from exc
        raise PhoneVerificationDeliveryError("Failed to send verification SMS.") from exc
    except BotoCoreError as exc:
        logger.warning("send_text_message failed", exc_info=True)
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
    Generate an OTP, store it in cache, and send it via AWS End User Messaging.
    Returns the verification status (``pending``).
    """
    aws_config = _assert_configured()
    _assert_send_allowed(phone_number)

    code = _random_code()
    cache.set(
        _otp_cache_key(phone_number),
        {"code_hash": make_password(code), "attempts": 0},
        timeout=OTP_TTL_SECONDS,
    )

    try:
        message = aws_config.render_sms_otp_message(code)
    except ValueError as exc:
        cache.delete(_otp_cache_key(phone_number))
        raise PhoneVerificationDeliveryError("SMS message template is invalid.") from exc

    message_id = _publish_sms(phone_number=phone_number, message=message, aws_config=aws_config)
    _record_send(phone_number)
    logger.info("Phone verification started: message_id=%s", message_id)
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


def publish_plain_sms(*, phone_number: str, message: str) -> str:
    """Send a plain SMS message via AWS End User Messaging (used by admin test-send)."""
    aws_config = _load_aws_config()
    if not aws_config.sns_configured:
        raise PhoneVerificationDeliveryError("SMS is not configured.")
    return _publish_sms(phone_number=phone_number, message=message, aws_config=aws_config)
