import logging
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Any

from django.core.cache import cache
from imap_tools import AND

from apps.mail.services.campaign.gmail_import.credential_mail import WITHOUT_CREDENTIAL_MAIL, without_credential_mail

from . import graph_backend
from .accounts import NO_ACCOUNTS_MESSAGE, readable_accounts, resolve_account
from .connection import (
    INBOX_FOLDER,
    INBOX_LIMIT_CHOICES,
    INBOX_LIST_CACHE_KEY,
    INBOX_LIST_CACHE_TTL,
    INBOX_MSG_CACHE_PREFIX,
    INBOX_MSG_CACHE_TTL,
    INBOX_STALE_LIST_CACHE_PREFIX,
    INBOX_STALE_LIST_CACHE_TTL,
    SENT_FOLDER,
    InboxBusy,
    InboxError,
)
from .formatting import build_snippet, extract_from, extract_to, format_date, timestamp_of

logger = logging.getLogger(__name__)


@dataclass
class InboxListing:
    """The newest messages of every inbox account, merged (``list_all_inbox_messages``).

    ``busy`` and ``unavailable`` name the accounts that could not be read now (held back by the delivery rate, or
    failing); a held-back account contributes the list it last read, and then ``showing_stale`` is set.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    busy: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    showing_stale: bool = False


def list_inbox_messages(
    limit: int = 30,
    mailbox: str | None = None,
    *,
    folder: str = INBOX_FOLDER,
    force_refresh: bool = False,
    account: str | None = None,
) -> list[dict[str, Any]]:
    """The newest messages of ``folder`` in one inbox account (``account``: its key; None: the default account),
    from the cache when fresh (a cache hit never reads the mailbox).

    While reads are held back, ``InboxBusy`` carries the last list read (``stale``) for the view to show.
    """
    return _list_account(resolve_account(account), limit, mailbox, folder=folder, force_refresh=force_refresh)


def list_all_inbox_messages(
    limit: int = 30, *, folder: str = INBOX_FOLDER, force_refresh: bool = False
) -> InboxListing:
    """The newest ``limit`` messages of ``folder`` across every inbox account, newest first.

    An account that cannot be read now is named in the listing instead of failing the whole inbox; ``InboxError``
    is raised only when no account is configured or none could be read at all.
    """
    accounts = readable_accounts()
    if not accounts:
        raise InboxError(NO_ACCOUNTS_MESSAGE)
    listing, merged = InboxListing(), []
    for account in accounts:
        try:
            merged.extend(_list_account(account, limit, None, folder=folder, force_refresh=force_refresh))
        except InboxBusy as exc:
            listing.busy.append(f"{account.address}: {exc}")
            if exc.stale is not None:
                listing.showing_stale = True
                merged.extend(exc.stale)
        except InboxError as exc:
            logger.warning("Inbox account %s could not be read: %s", account.key, exc)
            listing.unavailable.append(account.address)
        except Exception:
            logger.exception("Unexpected error reading inbox account %s.", account.key)
            listing.unavailable.append(account.address)
    if len(listing.unavailable) == len(accounts):
        raise InboxError("No inbox account could be read.")
    merged.sort(key=lambda message: message.get("timestamp") or 0.0, reverse=True)
    listing.messages = merged[:limit]
    return listing


def _list_account(account, limit: int, mailbox: str | None, *, folder: str, force_refresh: bool) -> list:
    suffix = f"{account.key}:{folder}:{limit}"
    cache_key = f"{INBOX_LIST_CACHE_KEY}:{suffix}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    try:
        results = _tagged(_read_list(account, mailbox, folder, limit), account)
    except InboxBusy as exc:
        exc.stale = cache.get(f"{INBOX_STALE_LIST_CACHE_PREFIX}{suffix}")
        raise
    cache.set(cache_key, results, INBOX_LIST_CACHE_TTL)
    cache.set(f"{INBOX_STALE_LIST_CACHE_PREFIX}{suffix}", results, INBOX_STALE_LIST_CACHE_TTL)
    return results


def _tagged(messages: list[dict[str, Any]], account) -> list[dict[str, Any]]:
    """Each message names the account it was read from, so a merged list links every row to its own mailbox."""
    for message in messages:
        message["account"] = account.key
        message["account_address"] = account.address
    return messages


def _read_list(account, mailbox: str | None, folder: str, limit: int) -> list[dict[str, Any]]:
    if account.is_graph:
        return graph_backend.list_messages(graph_backend.reader_for(account.address), folder=folder, limit=limit)
    try:
        import apps.mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox, folder=folder, account=account) as client:
            # The site's own credential mail is never listed from Sent (``credential_mail``): left out of the search
            # and dropped if it still comes back, before the list is cached.
            fetched = client.fetch(_list_search(folder), limit=limit, reverse=True, mark_seen=False, bulk=True)
            messages = _shown(fetched, folder)
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to list inbox messages.")
        raise InboxError("Failed to load inbox messages.") from exc
    return [message_summary(message) for message in messages]


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
        # Mail.Read cannot mark a message read, so the cached list keeps Outlook's read state.
        reader = graph_backend.reader_for(inbox_account.address)
        result = _tagged([graph_backend.fetch_message(reader, uid)], inbox_account)[0]
        cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
        return result

    try:
        import apps.mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox, folder=folder, account=inbox_account) as client:
            # The site's own credential mail is never opened or cached from Sent (``credential_mail``), as if it
            # were not there.
            fetched = client.fetch(_uid_search(folder, uid), limit=1, mark_seen=True, bulk=False)
            message = next(iter(_shown(fetched, folder)), None)
            if message is None:
                raise InboxError("Message not found.")
            result = _tagged([detailed_message(message)], inbox_account)[0]
        cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
        update_list_cache_seen(uid, folder=folder, account=inbox_account.key)
        return result
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch inbox message uid=%s.", uid)
        raise InboxError("Failed to fetch the message.") from exc


def _is_sent(folder: str) -> bool:
    # The credential tag is not authenticated, so it is honoured only in Sent (the account's own outgoing mail): a
    # tagged message received from outside is listed like any other (``credential_mail``).
    return str(folder or INBOX_FOLDER).upper() == SENT_FOLDER


def _list_search(folder: str):
    return WITHOUT_CREDENTIAL_MAIL if _is_sent(folder) else "ALL"


def _uid_search(folder: str, uid: str):
    return AND(WITHOUT_CREDENTIAL_MAIL, uid=uid) if _is_sent(folder) else AND(uid=uid)


def _shown(messages, folder: str) -> list:
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


def update_list_cache_seen(uid: str, folder: str = INBOX_FOLDER, account: str = "") -> None:
    """Mark an opened IMAP message read in the account's cached lists (opening it set ``\\Seen``)."""
    for limit in INBOX_LIMIT_CHOICES:
        cache_key = f"{INBOX_LIST_CACHE_KEY}:{account}:{folder}:{limit}"
        cached_list = cache.get(cache_key)
        if cached_list is None:
            continue
        for message in cached_list:
            if message["uid"] == uid:
                message["is_seen"] = True
                break
        cache.set(cache_key, cached_list, INBOX_LIST_CACHE_TTL)
