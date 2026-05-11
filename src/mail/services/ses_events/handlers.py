import logging
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from mail.models import RecipientLog

logger = logging.getLogger(__name__)

DIAG_MAX = 4000


def apply_bounce(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    bounce = ses_event.get("bounce", {})
    diag = diag_for_address(log.email_address, bounce.get("bouncedRecipients", []))
    log.status = "bounced"
    log.bounce_type = bounce.get("bounceType") or ""
    log.bounce_subtype = bounce.get("bounceSubType") or ""
    log.diagnostic_code = (diag.get("diagnosticCode") or "")[:DIAG_MAX]
    log.bounced_at = parse_ts(bounce.get("timestamp")) or timezone.now()
    _save_event_fields(log, "Bounce", log.bounced_at, sns_message_id)


def apply_complaint(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    complaint = ses_event.get("complaint", {})
    log.status = "complained"
    log.complaint_feedback_type = complaint.get("complaintFeedbackType") or ""
    log.complained_at = parse_ts(complaint.get("timestamp")) or timezone.now()
    _save_event_fields(log, "Complaint", log.complained_at, sns_message_id)


def apply_delivery(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    if log.status in {"bounced", "complained"}:
        return
    delivery = ses_event.get("delivery", {})
    log.status = "delivered"
    log.delivered_at = parse_ts(delivery.get("timestamp")) or timezone.now()
    _save_event_fields(log, "Delivery", log.delivered_at, sns_message_id)


def apply_delivery_delay(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    delay = ses_event.get("deliveryDelay", {})
    log.error_message = (
        f"Delayed: {delay.get('delayType', 'Unknown')} - expires " f"{delay.get('expirationTime', '')}"
    )[:DIAG_MAX]
    _save_event_fields(
        log,
        "DeliveryDelay",
        parse_ts(delay.get("timestamp")) or timezone.now(),
        sns_message_id,
        extra_fields=["error_message"],
    )


def apply_reject(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    reject = ses_event.get("reject", {})
    log.status = "rejected"
    log.error_message = (reject.get("reason") or "Rejected")[:DIAG_MAX]
    _save_event_fields(
        log,
        "Reject",
        timezone.now(),
        sns_message_id,
        extra_fields=["status", "error_message"],
    )


def noop_with_idempotency(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    log.last_sns_message_id = sns_message_id
    log.save(update_fields=["last_sns_message_id", "updated_at"])


def unknown(log: RecipientLog, ses_event: dict, sns_message_id: str) -> None:
    logger.info("Unknown SES event type; skipping")


EVENT_HANDLERS = {
    "Bounce": apply_bounce,
    "Complaint": apply_complaint,
    "Delivery": apply_delivery,
    "DeliveryDelay": apply_delivery_delay,
    "Reject": apply_reject,
    "Send": noop_with_idempotency,
    "Open": noop_with_idempotency,
    "Click": noop_with_idempotency,
}


def _save_event_fields(
    log: RecipientLog,
    event_type: str,
    event_at,
    sns_message_id: str,
    *,
    extra_fields: list[str] | None = None,
) -> None:
    log.last_event_type = event_type
    log.last_event_at = event_at
    log.last_sns_message_id = sns_message_id
    update_fields = [
        *(extra_fields or []),
        "last_event_type",
        "last_event_at",
        "last_sns_message_id",
        "updated_at",
    ]
    if event_type == "Bounce":
        update_fields = [
            "status",
            "bounce_type",
            "bounce_subtype",
            "diagnostic_code",
            "bounced_at",
            *update_fields,
        ]
    elif event_type == "Complaint":
        update_fields = [
            "status",
            "complaint_feedback_type",
            "complained_at",
            *update_fields,
        ]
    elif event_type == "Delivery":
        update_fields = ["status", "delivered_at", *update_fields]
    log.save(update_fields=update_fields)


def diag_for_address(address: str, bounced: list[dict]) -> dict:
    for entry in bounced:
        if (entry.get("emailAddress") or "").lower() == address.lower():
            return entry
    return bounced[0] if bounced else {}


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is not None:
        return parsed
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
