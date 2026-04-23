"""
Map AWS SNS / SES event payloads onto RecipientLog state.

Lookup strategy: every RecipientLog created by the campaign sender stores the
SES ``MessageId`` returned by ``send_raw_email``. Incoming SNS notifications
carry that same MessageId under ``mail.messageId``, so we can correlate events
in O(log n) via the indexed column. Transactional emails that don't register
a RecipientLog (e.g., ticket confirmations) produce zero-row lookups and are
silently ignored — that's the desired behavior.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from mail.models import RecipientLog

logger = logging.getLogger(__name__)

_DIAG_MAX = 4000


class SesEventError(Exception):
    """Raised when an SNS envelope can't be parsed or dispatched."""


def process_sns_envelope(envelope: dict[str, Any]) -> None:
    """Entry point invoked by the webhook view after signature verification."""
    msg_type = envelope.get("Type", "")
    if msg_type == "SubscriptionConfirmation":
        _handle_subscription_confirmation(envelope)
    elif msg_type == "UnsubscribeConfirmation":
        logger.info("SNS topic unsubscribed: %s", envelope.get("TopicArn"))
    elif msg_type == "Notification":
        _handle_notification(envelope)
    else:
        raise SesEventError(f"Unknown SNS Type: {msg_type!r}")


def _handle_subscription_confirmation(envelope: dict[str, Any]) -> None:
    subscribe_url = envelope.get("SubscribeURL", "")
    parsed = urlparse(subscribe_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host.endswith(".amazonaws.com"):
        logger.warning("Skipping SubscribeURL — unexpected host: %s", subscribe_url)
        return

    try:
        with urllib.request.urlopen(subscribe_url, timeout=5) as resp:  # noqa: S310  # https + allowlist
            resp.read()
        logger.info("SNS subscription confirmed for topic %s", envelope.get("TopicArn"))
    except Exception:
        logger.exception("Failed to auto-confirm SNS subscription")


def _handle_notification(envelope: dict[str, Any]) -> None:
    sns_message_id = envelope.get("MessageId", "")
    try:
        ses_event = json.loads(envelope.get("Message", ""))
    except json.JSONDecodeError as exc:
        raise SesEventError(f"SNS Message is not JSON: {exc}") from exc

    event_type = ses_event.get("eventType") or ses_event.get("notificationType") or ""
    mail_block = ses_event.get("mail", {})
    ses_message_id = mail_block.get("messageId", "")
    if not ses_message_id:
        logger.info("SES event without messageId; skipping (type=%s)", event_type)
        return

    handler = _EVENT_HANDLERS.get(event_type, _unknown)
    with transaction.atomic():
        logs = list(RecipientLog.objects.select_for_update().filter(ses_message_id=ses_message_id))
        for log in logs:
            if log.last_sns_message_id and log.last_sns_message_id == sns_message_id:
                continue
            handler(log, ses_event, sns_message_id)


def _apply_bounce(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    bounce = ses_event.get("bounce", {})
    diag = _diag_for_address(log.email_address, bounce.get("bouncedRecipients", []))

    log.status = "bounced"
    log.bounce_type = bounce.get("bounceType") or ""
    log.bounce_subtype = bounce.get("bounceSubType") or ""
    log.diagnostic_code = (diag.get("diagnosticCode") or "")[:_DIAG_MAX]
    log.bounced_at = _parse_ts(bounce.get("timestamp")) or timezone.now()
    log.last_event_type = "Bounce"
    log.last_event_at = log.bounced_at
    log.last_sns_message_id = sns_message_id
    log.save(
        update_fields=[
            "status",
            "bounce_type",
            "bounce_subtype",
            "diagnostic_code",
            "bounced_at",
            "last_event_type",
            "last_event_at",
            "last_sns_message_id",
            "updated_at",
        ]
    )


def _apply_complaint(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    complaint = ses_event.get("complaint", {})
    log.status = "complained"
    log.complaint_feedback_type = complaint.get("complaintFeedbackType") or ""
    log.complained_at = _parse_ts(complaint.get("timestamp")) or timezone.now()
    log.last_event_type = "Complaint"
    log.last_event_at = log.complained_at
    log.last_sns_message_id = sns_message_id
    log.save(
        update_fields=[
            "status",
            "complaint_feedback_type",
            "complained_at",
            "last_event_type",
            "last_event_at",
            "last_sns_message_id",
            "updated_at",
        ]
    )


def _apply_delivery(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    # A Delivery event arriving after a Bounce/Complaint must not overwrite
    # the terminal state we already recorded.
    if log.status in {"bounced", "complained"}:
        return
    delivery = ses_event.get("delivery", {})
    log.status = "delivered"
    log.delivered_at = _parse_ts(delivery.get("timestamp")) or timezone.now()
    log.last_event_type = "Delivery"
    log.last_event_at = log.delivered_at
    log.last_sns_message_id = sns_message_id
    log.save(
        update_fields=[
            "status",
            "delivered_at",
            "last_event_type",
            "last_event_at",
            "last_sns_message_id",
            "updated_at",
        ]
    )


def _apply_delivery_delay(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    delay = ses_event.get("deliveryDelay", {})
    log.last_event_type = "DeliveryDelay"
    log.last_event_at = _parse_ts(delay.get("timestamp")) or timezone.now()
    log.last_sns_message_id = sns_message_id
    log.error_message = (f"Delayed: {delay.get('delayType', 'Unknown')} — expires {delay.get('expirationTime', '')}")[
        :_DIAG_MAX
    ]
    # Status intentionally unchanged: delay is informational; the terminal
    # event (Bounce or Delivery) follows later.
    log.save(
        update_fields=[
            "last_event_type",
            "last_event_at",
            "last_sns_message_id",
            "error_message",
            "updated_at",
        ]
    )


def _apply_reject(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    reject = ses_event.get("reject", {})
    log.status = "rejected"
    log.error_message = (reject.get("reason") or "Rejected")[:_DIAG_MAX]
    log.last_event_type = "Reject"
    log.last_event_at = timezone.now()
    log.last_sns_message_id = sns_message_id
    log.save(
        update_fields=[
            "status",
            "error_message",
            "last_event_type",
            "last_event_at",
            "last_sns_message_id",
            "updated_at",
        ]
    )


def _noop_with_idempotency(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    log.last_sns_message_id = sns_message_id
    log.save(update_fields=["last_sns_message_id", "updated_at"])


def _unknown(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    logger.info(
        "Unknown SES event type for %s: %s",
        log.ses_message_id,
        ses_event.get("eventType") or ses_event.get("notificationType"),
    )


_EVENT_HANDLERS = {
    "Bounce": _apply_bounce,
    "Complaint": _apply_complaint,
    "Delivery": _apply_delivery,
    "DeliveryDelay": _apply_delivery_delay,
    "Reject": _apply_reject,
    "Send": _noop_with_idempotency,
    "Open": _noop_with_idempotency,
    "Click": _noop_with_idempotency,
}


def _diag_for_address(address: str, bounced: list[dict]) -> dict:
    for entry in bounced:
        if (entry.get("emailAddress") or "").lower() == address.lower():
            return entry
    return bounced[0] if bounced else {}


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is not None:
        return parsed
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
