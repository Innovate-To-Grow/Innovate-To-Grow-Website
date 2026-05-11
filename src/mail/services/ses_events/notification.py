import json
import logging
from typing import Any

from django.db import transaction

from mail.models import RecipientLog

from .handlers import EVENT_HANDLERS, unknown

logger = logging.getLogger(__name__)


def handle_notification(envelope: dict[str, Any]) -> None:
    import mail.services.ses_events as ses_api

    sns_message_id = envelope.get("MessageId", "")
    try:
        ses_event = json.loads(envelope.get("Message", ""))
    except json.JSONDecodeError as exc:
        raise ses_api.SesEventError("SNS Message is not JSON") from exc

    event_type = ses_event.get("eventType") or ses_event.get("notificationType") or ""
    ses_message_id = ses_event.get("mail", {}).get("messageId", "")
    if not ses_message_id:
        logger.info("SES event without messageId; skipping")
        return

    handler = EVENT_HANDLERS.get(event_type, unknown)
    with transaction.atomic():
        logs = list(RecipientLog.objects.select_for_update().filter(ses_message_id=ses_message_id))
        for log in logs:
            if log.last_sns_message_id and log.last_sns_message_id == sns_message_id:
                continue
            handler(log, ses_event, sns_message_id)
