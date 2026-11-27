"""Single inbox messages: opening one (``fetch_inbox_message``), the summary and detail dictionaries every backend
returns, and the Sent-folder credential-mail filters the lists share (``listing``)."""

import logging
from email.utils import parseaddr
from typing import Any

from django.core.cache import cache
from imap_tools import AND

from apps.mail.services.campaign.gmail_import.credential_mail import WITHOUT_CREDENTIAL_MAIL, without_credential_mail

from . import graph_backend
from .accounts import resolve_account
from .connection import INBOX_FOLDER, INBOX_MSG_CACHE_PREFIX, INBOX_MSG_CACHE_TTL, SENT_FOLDER, InboxError
from .formatting import build_snippet, extract_from, extract_to, format_date, timestamp_of

logger = logging.getLogger(__name__)


def fetch_inbox_message(
    uid: str, mailbox: str | None = None, *, folder: str = INBOX_FOLDER, account: str | None = None
) -> dict[str, Any]:
    """One message of an inbox account (``account``: its key; None: the default account)."""
    inbox_account = resolve_account(account)
    cache_key = f"{INBOX_MSG_CACHE_PREFIX}{inbox_account.key}:{folder}:{uid}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if inbox_account.is_graph:
        # The Graph reader only GETs, so opening never marks a message read in Outlook.
        reader = graph_backend.reader_for(inbox_account.address)
        result = tagged([graph_backend.fetch_message(reader, uid)], inbox_account)[0]
        cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
        return result

    try:
        import apps.mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox, folder=folder, account=inbox_account) as client:
            # BODY.PEEK (mark_seen=False): previewing a message never marks it read in Gmail, as with Graph, so the
            # lists, the snapshot and the unread count keep the mailbox's own read state. The site's own credential
            # mail is never opened or cached from Sent (``credential_mail``), as if it were not there.
            fetched = client.fetch(_uid_search(folder, uid), limit=1, mark_seen=False, bulk=False)
            message = next(iter(shown(fetched, folder)), None)
            if message is None:
                raise InboxError("Message not found.")
            result = tagged([detailed_message(message)], inbox_account)[0]
        cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
        return result
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch inbox message uid=%s.", uid)
        raise InboxError("Failed to fetch the message.") from exc


def tagged(messages: list[dict[str, Any]], account) -> list[dict[str, Any]]:
    """Each message names the account it was read from, so a merged list links every row to its own mailbox."""
    for message in messages:
        message["account"] = account.key
        message["account_address"] = account.address
    return messages


def _is_sent(folder: str) -> bool:
    # The credential tag is not authenticated, so it is honoured only in Sent (the account's own outgoing mail): a
    # tagged message received from outside is listed like any other (``credential_mail``).
    return str(folder or INBOX_FOLDER).upper() == SENT_FOLDER


def list_search(folder: str):
    return WITHOUT_CREDENTIAL_MAIL if _is_sent(folder) else "ALL"


def _uid_search(folder: str, uid: str):
    return AND(WITHOUT_CREDENTIAL_MAIL, uid=uid) if _is_sent(folder) else AND(uid=uid)


def shown(messages, folder: str) -> list:
    return without_credential_mail(messages) if _is_sent(folder) else list(messages)


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
        "timestamp": timestamp_of(getattr(message, "date", None)),
        "snippet": build_snippet(message),
        "is_seen": "\\Seen" in flags,
        "has_attachments": has_attachments(message),
        # IMAP UIDs are per folder, so the requested folder already says whether this is Sent mail.
        "from_own_mailbox": False,
    }


def has_attachments(message: Any) -> bool:
    """Whether a message has attachments: a listed one says so (``imap_list``), a whole one lists them."""
    flag = getattr(message, "has_attachments", None)
    if isinstance(flag, bool):
        return flag
    attachments = getattr(message, "attachments", None)
    return isinstance(attachments, list) and bool(attachments)


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
        "timestamp": timestamp_of(getattr(message, "date", None)),
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
