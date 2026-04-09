"""Helpers for importing recent Gmail sent-message HTML into campaigns."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from email.utils import parseaddr
from typing import Any

from bs4 import BeautifulSoup
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from imap_tools import AND, MailBox

from core.models import GmailImportConfig

from .preview import HTML_MARKER

logger = logging.getLogger(__name__)

GMAIL_LIST_CACHE_TTL = 300  # 5 minutes
GMAIL_MSG_CACHE_TTL = 1800  # 30 minutes

DEFAULT_GMAIL_MAILBOX = "i2g@g.ucmerced.edu"
DEFAULT_GMAIL_FOLDER = "Sent"
GMAIL_FOLDER_DISPLAY = "Sent mail (auto-detected)"
_SENT_FOLDER_CANDIDATES = (
    DEFAULT_GMAIL_FOLDER,
    "Sent Mail",
    "[Gmail]/Sent Mail",
    "[Google Mail]/Sent Mail",
)


class GmailImportError(RuntimeError):
    """Raised when Gmail message import cannot be completed."""


def _normalize_mailbox(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    parsed = parseaddr(normalized)[1]
    return parsed or normalized


def _get_gmail_config() -> GmailImportConfig:
    try:
        config = GmailImportConfig.load()
    except (OperationalError, ProgrammingError) as exc:
        raise GmailImportError("Gmail import configuration is unavailable. Run the latest migrations first.") from exc
    if not config.is_configured:
        raise GmailImportError("No active Gmail import account is configured.")
    return config


def resolve_gmail_mailbox(mailbox: str | None = None) -> str:
    explicit_mailbox = _normalize_mailbox(str(mailbox or "").strip())
    if explicit_mailbox:
        return explicit_mailbox

    try:
        config = GmailImportConfig.load()
    except (OperationalError, ProgrammingError):
        raise GmailImportError("Gmail import configuration is unavailable. Run the latest migrations first.")
    return _normalize_mailbox(config.mailbox) or DEFAULT_GMAIL_MAILBOX


def _iter_sent_folder_candidates(client) -> tuple[str, ...]:
    candidates: list[str] = []

    for folder_name in _SENT_FOLDER_CANDIDATES:
        if folder_name not in candidates:
            candidates.append(folder_name)

    try:
        for folder_info in client.folder.list():
            folder_name = str(getattr(folder_info, "name", "") or "").strip()
            folder_flags = tuple(getattr(folder_info, "flags", ()) or ())
            if "\\Sent" in folder_flags and folder_name and folder_name not in candidates:
                candidates.append(folder_name)
    except Exception:
        logger.debug("Unable to enumerate IMAP folders while selecting sent mail.", exc_info=True)

    return tuple(candidates)


def _select_sent_folder(client) -> str:
    for folder_name in _iter_sent_folder_candidates(client):
        try:
            client.folder.set(folder_name)
            return folder_name
        except Exception:
            continue

    raise GmailImportError("Unable to open the sent-mail folder for the configured Gmail account.")


@contextmanager
def _open_mailbox(mailbox: str | None = None):
    config = _get_gmail_config()
    resolved_mailbox = resolve_gmail_mailbox(mailbox or config.mailbox)
    try:
        with MailBox(config.imap_host).login(
            resolved_mailbox,
            config.gmail_password,
            initial_folder=None,
        ) as client:
            _select_sent_folder(client)
            yield client
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised in tests with mocks
        logger.exception("Failed to connect to Gmail IMAP for mailbox %s.", resolved_mailbox)
        raise GmailImportError(f"Unable to connect to Gmail for {resolved_mailbox}.") from exc


def _format_sent_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %I:%M %p %Z").strip()
    if value:
        return str(value)
    return ""


def _build_snippet(message: Any) -> str:
    html = str(getattr(message, "html", "") or "").strip()
    text = str(getattr(message, "text", "") or "").strip()
    source = html or text
    if not source:
        return ""

    snippet = " ".join(BeautifulSoup(source, "html.parser").get_text(" ").split())
    if len(snippet) > 160:
        return snippet[:157].rstrip() + "..."
    return snippet


def _normalize_html_fragment(html: str) -> str:
    normalized = str(html or "").strip()
    if not normalized:
        return ""

    soup = BeautifulSoup(normalized, "html.parser")
    if soup.body is not None:
        body_html = "".join(str(child) for child in soup.body.contents).strip()
        if body_html:
            return body_html
    return normalized


def _find_message_by_uid(mailbox, message_id: str):
    for message in mailbox.fetch(AND(uid=str(message_id)), limit=1, mark_seen=False, bulk=False):
        return message
    raise GmailImportError("The selected Gmail message could not be found.")


def list_recent_sent_messages(
    limit: int = 5, mailbox: str | None = None, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Return summaries for the most recent sent Gmail messages."""
    resolved_mailbox = resolve_gmail_mailbox(mailbox)
    cache_key = f"gmail_import:list:{resolved_mailbox}:{limit}"

    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        with _open_mailbox(mailbox=resolved_mailbox) as client:
            messages = list(client.fetch(limit=limit, reverse=True, mark_seen=False, bulk=True))
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised in tests with mocks
        logger.exception("Failed to list recent sent Gmail messages for %s.", resolved_mailbox)
        raise GmailImportError("Failed to load recent sent Gmail messages.") from exc

    summaries: list[dict[str, Any]] = []
    for message in messages:
        html = _normalize_html_fragment(getattr(message, "html", "") or "")
        summaries.append(
            {
                "message_id": str(getattr(message, "uid", "") or ""),
                "subject": str(getattr(message, "subject", "") or "").strip() or "(No subject)",
                "sent_at": _format_sent_at(getattr(message, "date", None)),
                "snippet": _build_snippet(message),
                "has_html": bool(html),
            }
        )

    cache.set(cache_key, summaries, GMAIL_LIST_CACHE_TTL)
    return summaries


def fetch_message_html_fragment(message_id: str, mailbox: str | None = None, *, use_cache: bool = True) -> str:
    """Fetch a Gmail message and return a wrapper-safe HTML fragment."""
    resolved_mailbox = resolve_gmail_mailbox(mailbox)
    cache_key = f"gmail_import:msg:{resolved_mailbox}:{message_id}"

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        with _open_mailbox(mailbox=resolved_mailbox) as client:
            message = _find_message_by_uid(client, message_id)
            html = _normalize_html_fragment(getattr(message, "html", "") or "")
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised in tests with mocks
        logger.exception("Failed to fetch Gmail message %s for %s.", message_id, resolved_mailbox)
        raise GmailImportError("Failed to fetch the selected Gmail message.") from exc

    if not html:
        raise GmailImportError("The selected Gmail message does not contain an HTML body.")
    cache.set(cache_key, html, GMAIL_MSG_CACHE_TTL)
    return html


def import_message_into_campaign(campaign, message_id: str, mailbox: str | None = None) -> str:
    """Import a Gmail HTML message into the given draft campaign."""
    html_fragment = fetch_message_html_fragment(message_id, mailbox=mailbox)
    campaign.body = HTML_MARKER + html_fragment
    campaign.save(update_fields=["body", "updated_at"])
    return campaign.body
