"""Services, constants and the logger the inbox views use; tests patch names here."""

import logging

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
    inbox_state_scope,
    list_all_inbox_messages,
    list_inbox_messages,
    paging,
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
    "InboxBusy",
    "InboxError",
    "analyze_email",
    "assess_email",
    "connectable_accounts",
    "default_identity_for",
    "fetch_inbox_message",
    "inbox_state_scope",
    "list_all_inbox_messages",
    "list_inbox_messages",
    "logger",
    "paging",
    "readable_accounts",
    "send_identities",
    "send_reply",
]
