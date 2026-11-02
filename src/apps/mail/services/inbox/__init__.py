"""Inbox viewer and reply service: Microsoft Graph or Gmail IMAP to read, the email facade to reply."""

from .connection import (
    INBOX_FOLDER,
    INBOX_FOLDER_CHOICES,
    INBOX_LIMIT_CHOICES,
    SENT_FOLDER,
    InboxBusy,
    InboxError,
    _open_inbox,
)
from .graph_backend import graph_inbox_active
from .messages import fetch_inbox_message, list_inbox_messages
from .reply import render_reply_html, send_reply

__all__ = [
    "INBOX_FOLDER",
    "INBOX_FOLDER_CHOICES",
    "INBOX_LIMIT_CHOICES",
    "SENT_FOLDER",
    "InboxBusy",
    "InboxError",
    "_open_inbox",
    "fetch_inbox_message",
    "graph_inbox_active",
    "list_inbox_messages",
    "render_reply_html",
    "send_reply",
]
