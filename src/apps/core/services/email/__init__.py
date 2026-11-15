"""Provider-neutral email delivery."""

from .gmail import GmailProvider
from .graph import GraphProvider
from .sending.contracts import DeliveryResult, EmailAttachment, EmailMessage, EmailProvider
from .sending.delivery import EmailDeliveryService, deliver_email
from .sending.exceptions import (
    EmailDeliveryError,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from .sending.registry import resolve_provider
from .ses import SESProvider
from .smtp import SMTPProvider
from .telemetry import email_tracking

__all__ = [
    "DeliveryResult",
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailDeliveryService",
    "EmailMessage",
    "EmailProvider",
    "GmailProvider",
    "GraphProvider",
    "PermanentEmailDeliveryError",
    "SESProvider",
    "SMTPProvider",
    "TransientEmailDeliveryError",
    "UncertainEmailDeliveryError",
    "deliver_email",
    "email_tracking",
    "resolve_provider",
]
