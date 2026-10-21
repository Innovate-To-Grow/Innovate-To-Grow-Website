"""Admin inbox views. Their services live in ``inbox.services`` (patch them there)."""

from .detail_views import inbox_detail_fragment_view, inbox_detail_view
from .list_views import inbox_fragment_view, inbox_list_view
from .reply_views import inbox_reply_fragment_view, inbox_reply_view
from .services import (
    INBOX_CONFIG_ERROR_MESSAGE,
    INBOX_DEFAULT_LIMIT,
    INBOX_FOLDER,
    INBOX_FOLDER_CHOICES,
    INBOX_LIMIT_CHOICES,
    INBOX_MESSAGE_ERROR_MESSAGE,
    INBOX_UNEXPECTED_ERROR_MESSAGE,
    SENT_FOLDER,
    InboxError,
    analyze_email,
    assess_email,
    fetch_inbox_message,
    list_inbox_messages,
    logger,
    send_reply,
)
from .urls import get_inbox_urls

__all__ = [
    "INBOX_FOLDER",
    "INBOX_FOLDER_CHOICES",
    "INBOX_LIMIT_CHOICES",
    "SENT_FOLDER",
    "InboxError",
    "analyze_email",
    "assess_email",
    "fetch_inbox_message",
    "get_inbox_urls",
    "inbox_detail_fragment_view",
    "inbox_detail_view",
    "inbox_fragment_view",
    "inbox_list_view",
    "inbox_reply_fragment_view",
    "inbox_reply_view",
    "list_inbox_messages",
    "logger",
    "send_reply",
]
