"""Public mail views and patch-compatible service aliases."""

# ruff: noqa: E402

from apps.mail.services.ses_events import SesEventError, process_sns_envelope
from apps.mail.services.sns_signature import SnsVerificationError, verify_sns_message

from .login_link import LoginLinkView
from .ses_webhook import SesEventThrottle, SesEventWebhookView, SnsEnvelopeParser
from .subscriptions import (
    OneClickUnsubscribeView,
    ResubscribeView,
)

__all__ = [
    "LoginLinkView",
    "OneClickUnsubscribeView",
    "ResubscribeView",
    "SesEventError",
    "SesEventThrottle",
    "SesEventWebhookView",
    "SnsEnvelopeParser",
    "SnsVerificationError",
    "process_sns_envelope",
    "verify_sns_message",
]
