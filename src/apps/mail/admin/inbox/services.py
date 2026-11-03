"""Services, constants and the logger the inbox views use; tests patch names here."""

import logging

from apps.mail.services.gmail_import.credential_mail import sent_copies_kept as gmail_sent_copies_kept
from apps.mail.services.inbox import (
    INBOX_FOLDER,
    INBOX_FOLDER_CHOICES,
    INBOX_LIMIT_CHOICES,
    SENT_FOLDER,
    InboxBusy,
    InboxError,
    fetch_inbox_message,
    graph_inbox_active,
    list_inbox_messages,
    send_reply,
)
from apps.mail.services.scam_detector import analyze_email, assess_email

# Keeps the package's historical logger name.
logger = logging.getLogger("apps.mail.admin.inbox")

INBOX_CONFIG_ERROR_MESSAGE = (
    "Inbox is not available. Check the Microsoft Graph mailbox scope or the Gmail import configuration."
)
INBOX_UNEXPECTED_ERROR_MESSAGE = "Inbox could not be loaded. Check server logs."
INBOX_MESSAGE_ERROR_MESSAGE = "Message could not be loaded. Check server logs."
INBOX_DEFAULT_LIMIT = 30
SENT_MAIL_DENIED_MESSAGE = "Sent mail of the sending mailbox is shown to staff with the Mail app only."

__all__ = [
    "INBOX_CONFIG_ERROR_MESSAGE",
    "INBOX_DEFAULT_LIMIT",
    "INBOX_FOLDER",
    "INBOX_FOLDER_CHOICES",
    "INBOX_LIMIT_CHOICES",
    "INBOX_MESSAGE_ERROR_MESSAGE",
    "INBOX_UNEXPECTED_ERROR_MESSAGE",
    "SENT_FOLDER",
    "SENT_MAIL_DENIED_MESSAGE",
    "InboxBusy",
    "InboxError",
    "analyze_email",
    "assess_email",
    "fetch_inbox_message",
    "gmail_sent_copies_kept",
    "graph_inbox_active",
    "list_inbox_messages",
    "logger",
    "send_reply",
]
