"""Helpers for importing recent Gmail sent-message HTML into campaigns."""

from __future__ import annotations

from imap_tools import MailBox

from core.models import GmailImportConfig

from .connection import (
    DEFAULT_GMAIL_FOLDER,
    DEFAULT_GMAIL_MAILBOX,
    GMAIL_FOLDER_DISPLAY,
    GmailImportError,
    _open_mailbox,
    resolve_gmail_mailbox,
)
from .messages import fetch_message_html_fragment, list_recent_sent_messages
from .persistence import import_message_into_campaign

__all__ = [
    "DEFAULT_GMAIL_FOLDER",
    "DEFAULT_GMAIL_MAILBOX",
    "GMAIL_FOLDER_DISPLAY",
    "GmailImportConfig",
    "GmailImportError",
    "MailBox",
    "_open_mailbox",
    "fetch_message_html_fragment",
    "import_message_into_campaign",
    "list_recent_sent_messages",
    "resolve_gmail_mailbox",
]
