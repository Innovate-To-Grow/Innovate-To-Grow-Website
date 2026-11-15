"""Email delivery: which provider sends (``service``, with its go-live checks in ``activation`` and its readiness in
``delivery_status``), the SMTP provider (``smtp``), and the Gmail IMAP account templates are imported from
(``imap_account``)."""

from .activation import GMAIL_ACTIVATION_REQUIRED, GMAIL_NOT_READY
from .imap_account import GmailAccessAccount
from .service import EmailServiceConfig
from .smtp import SMTPProviderConfig

__all__ = [
    "GMAIL_ACTIVATION_REQUIRED",
    "GMAIL_NOT_READY",
    "EmailServiceConfig",
    "GmailAccessAccount",
    "SMTPProviderConfig",
]
