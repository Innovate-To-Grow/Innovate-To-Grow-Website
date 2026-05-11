from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from django.core.cache import cache
from imap_tools import AND

from .connection import GmailImportError, resolve_gmail_mailbox

logger = logging.getLogger(__name__)

GMAIL_LIST_CACHE_TTL = 300
GMAIL_MSG_CACHE_TTL = 1800


def list_recent_sent_messages(
    limit: int = 5,
    mailbox: str | None = None,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    resolved_mailbox = resolve_gmail_mailbox(mailbox)
    cache_key = f"gmail_import:list:{resolved_mailbox}:{limit}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        import mail.services.gmail_import as gmail_api

        with gmail_api._open_mailbox(mailbox=resolved_mailbox) as client:
            messages = list(client.fetch(limit=limit, reverse=True, mark_seen=False, bulk=True))
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised in tests with mocks
        logger.exception("Failed to list recent sent Gmail messages for %s.", resolved_mailbox)
        raise GmailImportError("Failed to load recent sent Gmail messages.") from exc

    summaries = [message_summary(message) for message in messages]
    cache.set(cache_key, summaries, GMAIL_LIST_CACHE_TTL)
    return summaries


def fetch_message_html_fragment(
    message_id: str,
    mailbox: str | None = None,
    *,
    use_cache: bool = True,
) -> str:
    resolved_mailbox = resolve_gmail_mailbox(mailbox)
    cache_key = f"gmail_import:msg:{resolved_mailbox}:{message_id}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        import mail.services.gmail_import as gmail_api

        with gmail_api._open_mailbox(mailbox=resolved_mailbox) as client:
            message = find_message_by_uid(client, message_id)
            html = normalize_html_fragment(getattr(message, "html", "") or "")
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised in tests with mocks
        logger.exception("Failed to fetch Gmail message %s for %s.", message_id, resolved_mailbox)
        raise GmailImportError("Failed to fetch the selected Gmail message.") from exc

    if not html:
        raise GmailImportError("The selected Gmail message does not contain an HTML body.")
    cache.set(cache_key, html, GMAIL_MSG_CACHE_TTL)
    return html


def message_summary(message: Any) -> dict[str, Any]:
    html = normalize_html_fragment(getattr(message, "html", "") or "")
    return {
        "message_id": str(getattr(message, "uid", "") or ""),
        "subject": str(getattr(message, "subject", "") or "").strip() or "(No subject)",
        "sent_at": format_sent_at(getattr(message, "date", None)),
        "snippet": build_snippet(message),
        "has_html": bool(html),
    }


def format_sent_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %I:%M %p %Z").strip()
    if value:
        return str(value)
    return ""


def build_snippet(message: Any) -> str:
    html = str(getattr(message, "html", "") or "").strip()
    text = str(getattr(message, "text", "") or "").strip()
    source = html or text
    if not source:
        return ""
    snippet = " ".join(BeautifulSoup(source, "html.parser").get_text(" ").split())
    return snippet[:157].rstrip() + "..." if len(snippet) > 160 else snippet


def normalize_html_fragment(html: str) -> str:
    normalized = str(html or "").strip()
    if not normalized:
        return ""
    soup = BeautifulSoup(normalized, "html.parser")
    if soup.body is not None:
        body_html = "".join(str(child) for child in soup.body.contents).strip()
        if body_html:
            return body_html
    return normalized


def find_message_by_uid(mailbox, message_id: str):
    for message in mailbox.fetch(AND(uid=str(message_id)), limit=1, mark_seen=False, bulk=False):
        return message
    raise GmailImportError("The selected Gmail message could not be found.")
