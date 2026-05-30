import logging
from typing import Any

from .notification import handle_notification
from .subscription import handle_subscription_confirmation

logger = logging.getLogger(__name__)


class SesEventError(Exception):
    """Raised when an SNS envelope can't be parsed or dispatched."""


def process_sns_envelope(envelope: dict[str, Any]) -> None:
    msg_type = envelope.get("Type", "")
    if msg_type == "SubscriptionConfirmation":
        handle_subscription_confirmation(envelope)
    elif msg_type == "UnsubscribeConfirmation":
        logger.info("SNS topic unsubscribed")
    elif msg_type == "Notification":
        handle_notification(envelope)
    else:
        raise SesEventError("Unknown SNS Type")


__all__ = ["SesEventError", "process_sns_envelope"]
