"""Inbox admin helper functions."""

from html import escape
from urllib.parse import urlencode

from . import services as inbox_api


def message_load_error(exc) -> str:
    """What staff see when a message cannot be shown: when to try again while reads are held back, else the generic
    message (other errors may name hosts or accounts)."""
    return str(exc) if isinstance(exc, inbox_api.InboxBusy) else inbox_api.INBOX_MESSAGE_ERROR_MESSAGE


def parse_limit(request) -> int:
    """Parse and validate the requested inbox limit."""
    try:
        value = int(request.GET.get("limit", inbox_api.INBOX_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return inbox_api.INBOX_DEFAULT_LIMIT
    return value if value in inbox_api.INBOX_LIMIT_CHOICES else inbox_api.INBOX_DEFAULT_LIMIT


def parse_folder(request) -> str:
    """Parse and validate the requested inbox folder (INBOX or SENT)."""
    folder = str(request.GET.get("folder", inbox_api.INBOX_FOLDER)).upper()
    return folder if folder in inbox_api.INBOX_FOLDER_CHOICES else inbox_api.INBOX_FOLDER


def parse_account(request, *, default: str = "") -> str:
    """The requested inbox account key (``?account=``). The inbox services accept only a configured account's key,
    so this only trims it; ``default`` stands in when none is named."""
    value = str(request.GET.get("account", "") or "").strip()
    return value[:300] or default


def with_query(url: str, **params) -> str:
    """``url`` with the non-empty ``params`` as its query string (``urlencode``d)."""
    query = urlencode({key: value for key, value in params.items() if value})
    return f"{url}?{query}" if query else url


def message_body_html(msg: dict) -> str:
    """Return sanitized text fallback when a message has no HTML body."""
    if msg["html"]:
        return msg["html"]
    return f"<pre>{escape(msg['text'] or '')}</pre>"


def build_reply_references(msg: dict) -> str:
    """Build email References for a reply."""
    reply_references = msg.get("references", "")
    if msg.get("message_id"):
        if reply_references:
            return f"{reply_references} {msg['message_id']}"
        return msg["message_id"]
    return reply_references


def build_original_from(msg: dict) -> str:
    """Build display sender for quoted reply context."""
    original_from = msg["from_name"] or msg["from_email"]
    if msg["from_name"]:
        return f"{msg['from_name']} <{msg['from_email']}>"
    return original_from


def build_reply_subject(subject: str) -> str:
    """Prefix a subject with Re: when needed."""
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"
