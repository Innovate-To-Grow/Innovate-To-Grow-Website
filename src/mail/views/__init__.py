"""Public mail views and patch-compatible service aliases."""

# ruff: noqa: E402

import logging

from mail.services.ses_events import SesEventError, process_sns_envelope
from mail.services.sns_signature import SnsVerificationError, verify_sns_message

logger = logging.getLogger(__name__)

UNSUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired unsubscribe link."
RESUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired resubscribe link."

from .magic_login import MagicLoginView
from .ses_webhook import SesEventThrottle, SesEventWebhookView, SnsEnvelopeParser
from .subscriptions import (
    OneClickUnsubscribeView,
    ResubscribeView,
)

__all__ = [
    "MagicLoginView",
    "OneClickUnsubscribeView",
    "ResubscribeView",
    "SesEventError",
    "SesEventThrottle",
    "SesEventWebhookView",
    "SnsEnvelopeParser",
    "SnsVerificationError",
    "logger",
    "process_sns_envelope",
    "verify_sns_message",
]
