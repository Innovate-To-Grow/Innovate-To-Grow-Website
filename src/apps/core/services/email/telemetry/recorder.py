"""Saving telemetry rows. Best effort throughout: a failure is logged with its exception type only and swallowed, so
recording can never change whether or how an email is sent. Each write is a short transaction of its own (a
savepoint inside a caller's), so a failed write cannot break the caller's transaction either.
"""

import functools
import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Case, F, Value, When
from django.utils import timezone

from apps.core.models import EmailCategory, OutboundEmail, OutboundEmailAttempt

from . import text
from .context import TrackingContext, correlation_id

logger = logging.getLogger(__name__)
Status = OutboundEmail.Status
DeliveryStatus = OutboundEmail.DeliveryStatus
# Graph allows at most 500 recipients per message (the tenant up to 1,000): the stored list never needs more.
MAX_RECIPIENTS_KEPT = 1000


def monitoring_settings() -> dict:
    return settings.EMAIL_MONITORING


def enabled() -> bool:
    return bool(monitoring_settings()["telemetry_enabled"])


def best_effort(action):
    """Run ``action`` in its own (nested) transaction; on any error log the exception type and return None."""

    @functools.wraps(action)
    def wrapper(*args, **kwargs):
        try:
            with transaction.atomic():
                return action(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - telemetry must never change delivery.
            logger.warning("Email telemetry could not be saved (%s in %s)", type(exc).__name__, action.__name__)
            return None

    return wrapper


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def stored_subject(message) -> str:
    """The subject as the log may show it: none for a message that carries a credential (``keep_sent_copy=False``:
    a campaign subject may hold the recipient's login link), and token-shaped text scrubbed from any other."""
    if not monitoring_settings()["store_subjects"] or not message.keep_sent_copy:
        return ""
    return text.scrub(message.subject, 255)


def email_values(message, context: TrackingContext, *, provider: str) -> dict:
    """The columns of a new ``OutboundEmail`` for ``message`` sent under ``context``. The subject's digest is kept
    even when the subject is not, so bounce reports can still be matched to it."""
    recipients = text.addresses(message.envelope_recipients)
    subject = str(message.subject or "")
    category = context.category if context.category in EmailCategory.values else EmailCategory.OTHER
    return {
        "category": category,
        "subcategory": text.clean(context.subcategory, 100),
        "campaign_id": _uuid_or_none(context.campaign_id),
        "source_type": text.clean(context.source_type, 64),
        "source_id": text.clean(context.source_id, 64),
        "job_id": _uuid_or_none(context.job_id),
        "provider": text.clean(provider, 16),
        "recipient": recipients[0][:254] if recipients else "",
        "recipients": [item[:254] for item in recipients[:MAX_RECIPIENTS_KEPT]],
        "recipient_count": len(recipients),
        "subject": stored_subject(message),
        "subject_digest": text.subject_digest(subject),
    }


@best_effort
def open_email(message, context: TrackingContext, *, provider: str):
    """The id of the logical email for ``message``: found by its correlation id (a retry), else created."""
    values = email_values(message, context, provider=provider)
    key = correlation_id(context, values["recipients"], str(message.subject or ""))
    email, _created = OutboundEmail.objects.get_or_create(correlation_id=key, defaults=values)
    return email.pk


def _keep_or(status: str):
    """``status`` for an email still pending, its current status otherwise (an earlier attempt's answer stands)."""
    return Case(When(status=Status.PENDING, then=Value(status)), default=F("status"))


@best_effort
def record_deferral(email_id, *, retry_expected: bool, error: str) -> None:
    """The delivery rate held the email back before any provider call. Nothing retries a send without a retry key
    (a sign-in code: the person asks again, which is a new email), so that one is marked not sent."""
    values = {"deferral_count": F("deferral_count") + 1, "last_error_kind": "rate_deferred", "last_error": error}
    if not retry_expected:
        values["status"] = _keep_or(Status.NOT_SENT)
    OutboundEmail.objects.filter(pk=email_id).update(**values, updated_at=timezone.now())


@best_effort
def record_unsent(email_id, *, kind: str, error: str) -> None:
    """The site stopped the email before admitting it (configuration, mailbox scope, a delivery limit)."""
    OutboundEmail.objects.filter(pk=email_id).update(
        status=_keep_or(Status.NOT_SENT), last_error_kind=kind, last_error=error, updated_at=timezone.now()
    )


@best_effort
def open_attempt(email_id, *, provider: str, mailbox: str, job_attempt, started_at):
    """Number and save a new attempt (the email row is locked meanwhile, so concurrent attempts never share one)."""
    email = OutboundEmail.objects.select_for_update().get(pk=email_id)
    number = email.attempt_count + 1
    attempt = OutboundEmailAttempt.objects.create(
        email=email,
        attempt_number=number,
        provider=text.clean(provider, 16),
        started_at=started_at,
        job_attempt=job_attempt if isinstance(job_attempt, int) and 0 <= job_attempt < 32768 else None,
    )
    email.attempt_count = number
    email.status = Status.PENDING
    email.provider = text.clean(provider, 16) or email.provider
    email.mailbox = text.clean(mailbox, 254) or email.mailbox
    email.first_attempt_at = email.first_attempt_at or started_at
    email.last_attempt_at = started_at
    email.save(
        update_fields=[
            "attempt_count",
            "status",
            "provider",
            "mailbox",
            "first_attempt_at",
            "last_attempt_at",
            "updated_at",
        ]
    )
    return attempt.pk


@best_effort
def close_attempt(email_id, attempt_id, *, outcome: str, status: str, kind: str, error: str, notes, duration_ms):
    """Save how the attempt ended and roll it up into its email."""
    now = timezone.now()
    OutboundEmailAttempt.objects.filter(pk=attempt_id).update(
        outcome=outcome,
        error_kind=kind,
        operation=notes.operation or OutboundEmailAttempt.Operation.PROVIDER,
        endpoint=notes.endpoint[:128],
        http_status=notes.http_status,
        error_code=notes.error_code[:64],
        inner_error_code=notes.inner_error_code[:64],
        error_message=error,
        request_id=notes.request_id[:64],
        client_request_id=notes.client_request_id[:64],
        retry_after_seconds=notes.retry_after_seconds,
        token_fresh=notes.token_fresh,
        duration_ms=duration_ms,
        response_ms=notes.response_ms,
        diagnostics=notes.diagnostics,
        updated_at=now,
    )
    values = {
        "status": status,
        "last_http_status": notes.http_status,
        "total_duration_ms": F("total_duration_ms") + duration_ms,
        "updated_at": now,
    }
    if notes.internet_message_id:
        values["internet_message_id"] = notes.internet_message_id[:255]
    if notes.send_format:
        values["send_format"] = notes.send_format[:8]
    if status == Status.ACCEPTED:
        values["accepted_at"] = now
        values["delivery_status"] = Case(
            When(delivery_status=DeliveryStatus.NOT_APPLICABLE, then=Value(DeliveryStatus.UNKNOWN)),
            default=F("delivery_status"),
        )
    else:
        values.update(last_error_kind=kind, last_error_code=(notes.inner_error_code or notes.error_code)[:64])
        values["last_error"] = error
    OutboundEmail.objects.filter(pk=email_id).update(**values)
