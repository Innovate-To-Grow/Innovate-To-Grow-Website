"""Inbox admin helper functions."""

from html import escape

import mail.admin.inbox as inbox_api


def parse_limit(request) -> int:
    """Parse and validate the requested inbox limit."""
    try:
        value = int(request.GET.get("limit", inbox_api.INBOX_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return inbox_api.INBOX_DEFAULT_LIMIT
    return value if value in inbox_api.INBOX_LIMIT_CHOICES else inbox_api.INBOX_DEFAULT_LIMIT


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
