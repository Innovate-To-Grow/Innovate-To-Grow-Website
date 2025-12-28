import random
import string
import uuid
from datetime import timedelta
from typing import Iterable, Optional, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from authn.models.contact.contact_info import ContactEmail, ContactPhone

from ..models import BroadcastMessage, NotificationLog, Unsubscribe, VerificationRequest
from ..providers import send_email, send_sms


class RateLimitError(Exception):
    """Raised when sending exceeds the configured rate limit."""


class VerificationError(Exception):
    """Raised when verification fails."""


def _generate_numeric_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _check_rate_limit(channel: str, target: str, limit: int, window_minutes: int = 60) -> None:
    cutoff = timezone.now() - timedelta(minutes=window_minutes)
    recent_count = VerificationRequest.objects.filter(
        channel=channel,
        target=target,
        created_at__gte=cutoff,
    ).count()
    if recent_count >= limit:
        raise RateLimitError("Rate limit exceeded for this recipient.")


def issue_code(
    channel: str,
    target: str,
    purpose: str = "contact_verification",
    code_length: int = 6,
    expires_in_minutes: int = 10,
    max_attempts: int = 5,
    rate_limit_per_hour: int = 5,
) -> VerificationRequest:
    """
    Create and send a verification code.
    """
    _check_rate_limit(channel, target, rate_limit_per_hour)

    code = _generate_numeric_code(code_length)
    expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)

    verification = VerificationRequest.objects.create(
        channel=channel,
        method=VerificationRequest.METHOD_CODE,
        target=target,
        purpose=purpose,
        code=code,
        expires_at=expires_at,
        max_attempts=max_attempts,
    )

    message = f"Your verification code is: {code}. It expires in {expires_in_minutes} minutes."
    if channel == VerificationRequest.CHANNEL_EMAIL:
        send_email(target, subject="Your verification code", body=message)
    else:
        send_sms(target, message=message)

    return verification


def issue_link(
    channel: str,
    target: str,
    purpose: str = "contact_verification",
    expires_in_minutes: int = 60,
    max_attempts: int = 5,
    rate_limit_per_hour: int = 5,
    base_url: Optional[str] = None,
) -> Tuple[VerificationRequest, str]:
    """
    Create and send a verification link token. Returns the verification record and the URL.
    """
    _check_rate_limit(channel, target, rate_limit_per_hour)

    token = uuid.uuid4().hex
    expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)

    verification = VerificationRequest.objects.create(
        channel=channel,
        method=VerificationRequest.METHOD_LINK,
        target=target,
        purpose=purpose,
        token=token,
        expires_at=expires_at,
        max_attempts=max_attempts,
    )

    link = token if base_url is None else f"{base_url.rstrip('/')}/{token}"
    message = f"Click to verify: {link} (expires in {expires_in_minutes} minutes)."

    if channel == VerificationRequest.CHANNEL_EMAIL:
        send_email(target, subject="Verify your email", body=message)
    else:
        send_sms(target, message=message)

    return verification, link


def verify_code(
    channel: str,
    target: str,
    submitted_code: str,
    purpose: str = "contact_verification",
) -> bool:
    """
    Validate a verification code for the target/channel/purpose.
    """
    verification = (
        VerificationRequest.objects.filter(
            channel=channel,
            target=target,
            method=VerificationRequest.METHOD_CODE,
            purpose=purpose,
        )
        .order_by("-created_at")
        .first()
    )

    if not verification:
        raise VerificationError("No verification code found.")

    now = timezone.now()
    if verification.expires_at <= now:
        verification.status = VerificationRequest.STATUS_EXPIRED
        verification.save(update_fields=["status"])
        raise VerificationError("Verification code expired.")

    if verification.attempts >= verification.max_attempts:
        verification.status = VerificationRequest.STATUS_FAILED
        verification.save(update_fields=["status"])
        raise VerificationError("Maximum attempts exceeded.")

    if verification.code != submitted_code:
        verification.attempts += 1
        if verification.attempts >= verification.max_attempts:
            verification.status = VerificationRequest.STATUS_FAILED
            verification.save(update_fields=["attempts", "status"])
            raise VerificationError("Maximum attempts exceeded.")

        verification.save(update_fields=["attempts"])
        raise VerificationError("Invalid verification code.")

    verification.status = VerificationRequest.STATUS_VERIFIED
    verification.verified_at = now
    verification.save(update_fields=["status", "verified_at"])
    return True


def verify_link(token: str, purpose: str = "contact_verification") -> bool:
    """
    Validate a verification link token.
    """
    verification = (
        VerificationRequest.objects.filter(
            token=token,
            method=VerificationRequest.METHOD_LINK,
            purpose=purpose,
        )
        .order_by("-created_at")
        .first()
    )

    if not verification:
        raise VerificationError("Invalid verification link.")

    now = timezone.now()
    if verification.expires_at <= now:
        verification.status = VerificationRequest.STATUS_EXPIRED
        verification.save(update_fields=["status"])
        raise VerificationError("Verification link expired.")

    if verification.status == VerificationRequest.STATUS_VERIFIED:
        return True

    verification.status = VerificationRequest.STATUS_VERIFIED
    verification.verified_at = now
    verification.save(update_fields=["status", "verified_at"])
    return True


def send_notification(
    channel: str,
    target: str,
    message: str,
    subject: str = "",
    provider: str | None = None,
) -> NotificationLog:
    """
    Send a generic notification (email/SMS) and persist a delivery log.
    """
    with transaction.atomic():
        log = NotificationLog.objects.create(
            channel=channel,
            target=target,
            subject=subject or "",
            message=message,
            provider=provider or "console",
        )

        success = False
        provider_name = provider or "console"
        error_message = ""

        if channel == VerificationRequest.CHANNEL_EMAIL:
            success, provider_name = send_email(target, subject=subject or "Notification", body=message, provider=provider)
        else:
            success, provider_name = send_sms(target, message=message, provider=provider)

        if success:
            log.status = NotificationLog.STATUS_SENT
            log.provider = provider_name
            log.sent_at = timezone.now()
            log.save(update_fields=["status", "provider", "sent_at"])
        else:
            log.status = NotificationLog.STATUS_FAILED
            log.error_message = error_message or "Failed to send notification."
            log.provider = provider_name
            log.save(update_fields=["status", "error_message", "provider"])

        return log


def _get_unsubscribed_targets(channel: str, scope: str) -> set[str]:
    scope_filter = Q(scope=scope) | Q(scope="general")
    return set(
        Unsubscribe.objects.filter(channel=channel)
        .filter(scope_filter)
        .values_list("target", flat=True)
    )


def _iter_subscribers(channel: str) -> Iterable[str]:
    if channel == VerificationRequest.CHANNEL_EMAIL:
        queryset = ContactEmail.objects.filter(subscribe=True).order_by("id")
        for contact in queryset.iterator():
            yield contact.email_address
    else:
        queryset = ContactPhone.objects.filter(subscribe=True).order_by("id")
        for contact in queryset.iterator():
            yield contact.get_formatted_number()


def send_broadcast_message(broadcast: BroadcastMessage) -> BroadcastMessage:
    """
    Deliver the broadcast content to all subscribed contacts for the given channel.
    """

    if not broadcast.is_sendable:
        return broadcast

    broadcast.status = BroadcastMessage.STATUS_SENDING
    broadcast.total_recipients = 0
    broadcast.sent_count = 0
    broadcast.failed_count = 0
    broadcast.last_error = ""
    broadcast.sent_at = None
    broadcast.save(
        update_fields=[
            "status",
            "total_recipients",
            "sent_count",
            "failed_count",
            "last_error",
            "sent_at",
            "updated_at",
        ]
    )

    unsubscribed = _get_unsubscribed_targets(broadcast.channel, broadcast.scope)

    for target in _iter_subscribers(broadcast.channel):
        if target in unsubscribed:
            continue

        broadcast.total_recipients += 1
        try:
            log = send_notification(
                channel=broadcast.channel,
                target=target,
                subject=broadcast.subject or broadcast.name,
                message=broadcast.message,
            )
            if log.status == NotificationLog.STATUS_SENT:
                broadcast.sent_count += 1
            else:
                broadcast.failed_count += 1
        except Exception as exc:  # pragma: no cover - defensive
            broadcast.failed_count += 1
            broadcast.last_error = str(exc)

    if broadcast.total_recipients == 0:
        broadcast.status = BroadcastMessage.STATUS_FAILED
        broadcast.last_error = "No subscribed recipients available for this broadcast."
        broadcast.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )
        raise ValueError(broadcast.last_error)

    if broadcast.failed_count and broadcast.sent_count:
        broadcast.status = BroadcastMessage.STATUS_PARTIAL
    elif broadcast.failed_count and not broadcast.sent_count:
        broadcast.status = BroadcastMessage.STATUS_FAILED
    else:
        broadcast.status = BroadcastMessage.STATUS_SENT

    broadcast.sent_at = timezone.now()
    broadcast.save(
        update_fields=[
            "status",
            "total_recipients",
            "sent_count",
            "failed_count",
            "last_error",
            "sent_at",
            "updated_at",
        ]
    )

    return broadcast

