import random
import string
import uuid
from collections.abc import Iterable
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from authn.models.contact.contact_info import ContactEmail, ContactPhone

from ..models import (
    BroadcastMessage,
    EmailLayout,
    EmailMessageLayout,
    NotificationLog,
    Unsubscribe,
    VerificationRequest,
)
from ..providers.email import send_email
from ..providers.message import send_sms


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


def _render_email_template(
    *,
    template_key: str,
    context: dict | None,
    recipient_email: str,
    fallback_subject: str,
    fallback_body: str,
) -> tuple[str, str, dict, EmailLayout | None]:
    layout = EmailMessageLayout.objects.filter(key=template_key, is_active=True).first()
    if not layout:
        return fallback_subject, fallback_body, context or {}, None

    subject, body, preheader, ctx = layout.render(context=context, recipient_email=recipient_email)
    if preheader:
        ctx = {**ctx, "preheader": preheader}

    base_layout = layout.layout if getattr(layout, "layout", None) and layout.layout.is_active else None
    return subject or fallback_subject, body or fallback_body, ctx, base_layout


def issue_code(
    channel: str,
    target: str,
    purpose: str = "contact_verification",
    code_length: int = 6,
    expires_in_minutes: int = 10,
    max_attempts: int = 5,
    rate_limit_per_hour: int = 5,
    context: dict | None = None,
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
        email_context = dict(context or {})
        email_context.update({"code": code, "expires_in_minutes": expires_in_minutes})
        default_subject = "Your verification code"
        default_body = (
            "Hi {{ recipient_name }},\n\n"
            "Your verification code is: {{ code }}.\n"
            "It expires in {{ expires_in_minutes }} minutes.\n\n"
            "If you did not request this, you can ignore this email."
        )
        subject, body, rendered_context, base_layout = _render_email_template(
            template_key="verification_code",
            context=email_context,
            recipient_email=target,
            fallback_subject=default_subject,
            fallback_body=default_body,
        )
        send_email(target, subject=subject, body=body, context=rendered_context, layout=base_layout)
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
    base_url: str | None = None,
    context: dict | None = None,
) -> tuple[VerificationRequest, str]:
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
        email_context = dict(context or {})
        email_context.update({"verification_link": link, "link": link, "expires_in_minutes": expires_in_minutes})
        default_subject = "Verify your email"
        default_body = (
            "Hi {{ recipient_name }},\n\n"
            "Please verify your email by clicking the link below:\n"
            "{{ verification_link }}\n\n"
            "This link expires in {{ expires_in_minutes }} minutes."
        )
        subject, body, rendered_context, base_layout = _render_email_template(
            template_key="verification_link",
            context=email_context,
            recipient_email=target,
            fallback_subject=default_subject,
            fallback_body=default_body,
        )
        send_email(target, subject=subject, body=body, context=rendered_context, layout=base_layout)
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
    context: dict | None = None,
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
            success, provider_name = send_email(
                target,
                subject=subject or "Notification",
                body=message,
                provider=provider,
                context=context,
            )
        else:
            success, provider_name = send_sms(target, message=message, provider=provider)

        if not success and not error_message:
            error_message = f"Failed to send notification via provider '{provider_name}'."

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
    return set(Unsubscribe.objects.filter(channel=channel).filter(scope_filter).values_list("target", flat=True))


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
