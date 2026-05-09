import logging
from typing import Any

from django.core.cache import cache
from imap_tools import AND

from .connection import (
    INBOX_LIMIT_CHOICES,
    INBOX_LIST_CACHE_KEY,
    INBOX_LIST_CACHE_TTL,
    INBOX_MSG_CACHE_PREFIX,
    INBOX_MSG_CACHE_TTL,
    InboxError,
)
from .formatting import build_snippet, extract_from, extract_to, format_date

logger = logging.getLogger(__name__)


def list_inbox_messages(
    limit: int = 30,
    mailbox: str | None = None,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    cache_key = f"{INBOX_LIST_CACHE_KEY}:{limit}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        import mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox) as client:
            messages = list(client.fetch(limit=limit, reverse=True, mark_seen=False, bulk=True))
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to list inbox messages.")
        raise InboxError("Failed to load inbox messages.") from exc

    results = [message_summary(message) for message in messages]
    cache.set(cache_key, results, INBOX_LIST_CACHE_TTL)
    return results


def fetch_inbox_message(uid: str, mailbox: str | None = None) -> dict[str, Any]:
    cache_key = f"{INBOX_MSG_CACHE_PREFIX}{uid}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox) as client:
            for message in client.fetch(AND(uid=uid), limit=1, mark_seen=True, bulk=False):
                result = detailed_message(message)
                cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
                update_list_cache_seen(uid)
                return result
            raise InboxError("Message not found.")
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch inbox message uid=%s.", uid)
        raise InboxError("Failed to fetch the message.") from exc


def message_summary(message: Any) -> dict[str, Any]:
    from_name, from_email = extract_from(message)
    flags = set(getattr(message, "flags", ()) or ())
    return {
        "uid": str(getattr(message, "uid", "") or ""),
        "subject": str(getattr(message, "subject", "") or "").strip() or "(No subject)",
        "from_name": from_name,
        "from_email": from_email,
        "date": format_date(getattr(message, "date", None)),
        "snippet": build_snippet(message),
        "is_seen": "\\Seen" in flags,
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
    }


def update_list_cache_seen(uid: str) -> None:
    for limit in INBOX_LIMIT_CHOICES:
        cache_key = f"{INBOX_LIST_CACHE_KEY}:{limit}"
        cached_list = cache.get(cache_key)
        if cached_list is None:
            continue
        for message in cached_list:
            if message["uid"] == uid:
                message["is_seen"] = True
                break
        cache.set(cache_key, cached_list, INBOX_LIST_CACHE_TTL)
