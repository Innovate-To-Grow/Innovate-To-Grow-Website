"""Admin inbox view package with patch-compatible service aliases."""

# ruff: noqa: E402

import logging

from mail.services.inbox import INBOX_LIMIT_CHOICES, InboxError, fetch_inbox_message, list_inbox_messages, send_reply
from mail.services.scam_detector import analyze_email

logger = logging.getLogger(__name__)

INBOX_CONFIG_ERROR_MESSAGE = "Inbox is not available. Check Gmail import configuration."
INBOX_UNEXPECTED_ERROR_MESSAGE = "Inbox could not be loaded. Check server logs."
INBOX_MESSAGE_ERROR_MESSAGE = "Message could not be loaded. Check server logs."
INBOX_DEFAULT_LIMIT = 30

from .detail_views import inbox_detail_fragment_view, inbox_detail_view
from .list_views import inbox_fragment_view, inbox_list_view
from .reply_views import inbox_reply_fragment_view, inbox_reply_view
from .urls import get_inbox_urls

__all__ = [
    "INBOX_LIMIT_CHOICES",
    "InboxError",
    "analyze_email",
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
