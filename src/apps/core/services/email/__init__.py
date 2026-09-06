"""Provider-neutral email delivery."""

from .contracts import DeliveryResult, EmailAttachment, EmailMessage, EmailProvider
from .delivery import EmailDeliveryService, deliver_email
from .exceptions import (
    EmailDeliveryError,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from .registry import resolve_provider
from .ses import SESProvider
from .smtp import SMTPProvider

__all__ = [
    "DeliveryResult",
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailDeliveryService",
    "EmailMessage",
    "EmailProvider",
    "PermanentEmailDeliveryError",
    "SESProvider",
    "SMTPProvider",
    "TransientEmailDeliveryError",
    "UncertainEmailDeliveryError",
    "deliver_email",
    "resolve_provider",
]
