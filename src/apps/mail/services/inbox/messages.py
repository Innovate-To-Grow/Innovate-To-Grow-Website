import logging
from email.utils import parseaddr
from typing import Any

from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from imap_tools import AND

from . import graph_backend
from .connection import (
    INBOX_FOLDER,
    INBOX_LIMIT_CHOICES,
    INBOX_LIST_CACHE_KEY,
    INBOX_LIST_CACHE_TTL,
    INBOX_MSG_CACHE_PREFIX,
    INBOX_MSG_CACHE_TTL,
    INBOX_STALE_LIST_CACHE_PREFIX,
    INBOX_STALE_LIST_CACHE_TTL,
    InboxBusy,
    InboxError,
)
from .formatting import build_snippet, extract_from, extract_to, format_date

logger = logging.getLogger(__name__)


def list_inbox_messages(
    limit: int = 30,
    mailbox: str | None = None,
    *,
    folder: str = INBOX_FOLDER,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """The newest messages of ``folder``, from the cache when fresh (a cache hit never reads the mailbox).

    While reads are held back, ``InboxBusy`` carries the last list read (``stale``) for the view to show.
    """
    reader = _graph_reader()
    suffix = f"{_backend(reader)}{folder}:{limit}"
    cache_key = f"{INBOX_LIST_CACHE_KEY}:{suffix}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    try:
        results = _read_list(reader, mailbox, folder, limit)
    except InboxBusy as exc:
        exc.stale = cache.get(f"{INBOX_STALE_LIST_CACHE_PREFIX}{suffix}")
        raise
    cache.set(cache_key, results, INBOX_LIST_CACHE_TTL)
    cache.set(f"{INBOX_STALE_LIST_CACHE_PREFIX}{suffix}", results, INBOX_STALE_LIST_CACHE_TTL)
    return results


def _read_list(reader, mailbox: str | None, folder: str, limit: int) -> list[dict[str, Any]]:
    if reader is not None:
        return graph_backend.list_messages(reader, folder=folder, limit=limit)
    try:
        import apps.mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox, folder=folder) as client:
            messages = list(client.fetch(limit=limit, reverse=True, mark_seen=False, bulk=True))
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to list inbox messages.")
        raise InboxError("Failed to load inbox messages.") from exc
    return [message_summary(message) for message in messages]


def fetch_inbox_message(uid: str, mailbox: str | None = None, *, folder: str = INBOX_FOLDER) -> dict[str, Any]:
    reader = _graph_reader()
    cache_key = f"{INBOX_MSG_CACHE_PREFIX}{_backend(reader)}{folder}:{uid}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if reader is not None:
        # Mail.Read cannot mark a message read, so the cached list keeps Outlook's read state.
        result = graph_backend.fetch_message(reader, uid)
        cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
        return result

    try:
        import apps.mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox, folder=folder) as client:
            for message in client.fetch(AND(uid=uid), limit=1, mark_seen=True, bulk=False):
                result = detailed_message(message)
                cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
                update_list_cache_seen(uid, folder=folder)
                return result
            raise InboxError("Message not found.")
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch inbox message uid=%s.", uid)
        raise InboxError("Failed to fetch the message.") from exc


def _graph_reader():
    """The Microsoft Graph reader when Graph has read permission on the I2G mailbox, else None (Gmail IMAP)."""
    try:
        return graph_backend.active_reader()
    except (OperationalError, ProgrammingError) as exc:
        raise InboxError("Mail configuration is unavailable. Run the latest migrations first.") from exc


def _backend(reader) -> str:
    # Graph and IMAP message ids differ, so their cached lists and messages must never be mixed.
    return "graph:" if reader is not None else ""


def message_summary(message: Any) -> dict[str, Any]:
    from_name, from_email = extract_from(message)
    flags = set(getattr(message, "flags", ()) or ())
    return {
        "uid": str(getattr(message, "uid", "") or ""),
        "subject": str(getattr(message, "subject", "") or "").strip() or "(No subject)",
        "from_name": from_name,
        "from_email": from_email,
        "to": extract_to(message),
        "date": format_date(getattr(message, "date", None)),
        "snippet": build_snippet(message),
        "is_seen": "\\Seen" in flags,
        # IMAP UIDs are per folder, so the requested folder already says whether this is Sent mail.
        "from_own_mailbox": False,
    }


def detailed_message(message: Any) -> dict[str, Any]:
    from_name, from_email = extract_from(message)
    headers = getattr(message, "headers", {}) or {}
    message_id_list = headers.get("message-id", [])
    references_list = headers.get("references", [])
    return {
        "uid": str(getattr(message, "uid", "") or ""),
        "subject": str(getattr(message, "subject", "") or "").strip() or "(No subject)",
        "from_name": from_name,
        "from_email": from_email,
        "to": extract_to(message),
        "date": format_date(getattr(message, "date", None)),
        "html": str(getattr(message, "html", "") or "").strip(),
        "text": str(getattr(message, "text", "") or "").strip(),
        "message_id": str(message_id_list[0]) if message_id_list else "",
        "references": str(references_list[0]) if references_list else "",
        # Authentication / routing headers the scam detector inspects (Gmail
        # populates Authentication-Results). Empty strings when absent.
        "reply_to": _header_address(headers, "reply-to"),
        "return_path": _header_address(headers, "return-path"),
        "authentication_results": " ".join(headers.get("authentication-results", []) or []),
        # IMAP UIDs are per folder, so the requested folder already says whether this is Sent mail.
        "from_own_mailbox": False,
    }


def _header_address(headers: dict[str, Any], key: str) -> str:
    values = headers.get(key, []) or []
    return parseaddr(values[0])[1].strip().lower() if values else ""


def update_list_cache_seen(uid: str, folder: str = INBOX_FOLDER) -> None:
    for limit in INBOX_LIMIT_CHOICES:
        cache_key = f"{INBOX_LIST_CACHE_KEY}:{folder}:{limit}"
        cached_list = cache.get(cache_key)
        if cached_list is None:
            continue
        for message in cached_list:
            if message["uid"] == uid:
                message["is_seen"] = True
                break
        cache.set(cache_key, cached_list, INBOX_LIST_CACHE_TTL)
