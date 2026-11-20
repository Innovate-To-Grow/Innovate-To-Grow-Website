"""Services, constants and the logger the inbox views use; tests patch names here."""

import logging

from apps.mail.services.campaign.gmail_import.credential_mail import sent_copies_kept as gmail_sent_copies_kept
from apps.mail.services.inbox import (
    ALL_ACCOUNTS,
    DEFAULT_SENDER,
    INBOX_FOLDER,
    INBOX_FOLDER_CHOICES,
    INBOX_LIMIT_CHOICES,
    SENT_FOLDER,
    InboxBusy,
    InboxError,
    connectable_accounts,
    default_identity_for,
    fetch_inbox_message,
    graph_inbox_active,
    list_all_inbox_messages,
    list_inbox_messages,
    readable_accounts,
    send_identities,
    send_reply,
)
from apps.mail.services.scam_detector import analyze_email, assess_email

# Keeps the package's historical logger name.
logger = logging.getLogger("apps.mail.admin.inbox")

INBOX_CONFIG_ERROR_MESSAGE = (
    "Inbox is not available. Check the Microsoft Graph mailbox scope or the Gmail access accounts."
)
INBOX_UNEXPECTED_ERROR_MESSAGE = "Inbox could not be loaded. Check server logs."
INBOX_MESSAGE_ERROR_MESSAGE = "Message could not be loaded. Check server logs."
INBOX_DEFAULT_LIMIT = 30
SENT_MAIL_DENIED_MESSAGE = "Sent mail of the sending mailbox is shown to staff with the Mail app only."

__all__ = [
    "ALL_ACCOUNTS",
    "DEFAULT_SENDER",
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
    "connectable_accounts",
    "default_identity_for",
    "fetch_inbox_message",
    "gmail_sent_copies_kept",
    "graph_inbox_active",
    "list_all_inbox_messages",
    "list_inbox_messages",
    "logger",
    "readable_accounts",
    "send_identities",
    "send_reply",
]
