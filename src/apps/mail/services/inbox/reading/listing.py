"""Inbox lists: the newest messages of one account, or of every account merged.

A list comes from this container's cache, else the background poll's fresh Inbox snapshot (``polling.health``),
else a live read whose outcome is recorded for every container (``polling.records``).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from django.core.cache import cache

from ..polling import health
from . import graph_backend
from .accounts import NO_ACCOUNTS_MESSAGE, connectable_accounts, resolve_account
from .connection import (
    INBOX_FOLDER,
    INBOX_LIST_CACHE_KEY,
    INBOX_LIST_CACHE_TTL,
    INBOX_STALE_LIST_CACHE_PREFIX,
    INBOX_STALE_LIST_CACHE_TTL,
    InboxBusy,
    InboxError,
)
from .messages import list_search, message_summary, shown, tagged

logger = logging.getLogger(__name__)

# A list served from the poller's snapshot is kept this briefly in a container's cache: the next poll may add mail.
INBOX_SNAPSHOT_CACHE_TTL = 30


@dataclass
class InboxListing:
    """The newest messages of every inbox account, merged (``list_all_inbox_messages``).

    ``busy`` and ``unavailable`` name the accounts that could not be read now (held back by the delivery rate, or
    failing); a held-back account contributes the list it last read, and then ``showing_stale`` is set. ``hidden``
    names the accounts left out because they could not connect recently (``health``; Refresh tries them again).
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    busy: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)
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

    Accounts that could not connect recently are left out (``connectable_accounts``; ``force_refresh`` tries them
    all again, and so does a list whose every account is left out). An account that cannot be read now is named in
    the listing instead of failing the whole inbox; ``InboxError`` is raised only when no account is configured or
    none could be read at all.
    """
    accounts, hidden = connectable_accounts(retry=force_refresh)
    if not accounts:
        accounts, hidden = hidden, []
    if not accounts:
        raise InboxError(NO_ACCOUNTS_MESSAGE)
    listing, merged = InboxListing(hidden=[account.address for account in hidden]), []
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
    """One account's list: this container's cache, else the poller's fresh Inbox snapshot, else a live read, whose
    outcome is recorded for every container. ``force_refresh`` always reads live."""
    suffix = f"{account.key}:{folder}:{limit}"
    cache_key = f"{INBOX_LIST_CACHE_KEY}:{suffix}"
    use_snapshot = folder == INBOX_FOLDER and not mailbox
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        snapshot = health.fresh_snapshot(account, limit) if use_snapshot else None
        if snapshot is not None:
            # Kept briefly, so the next poll's mail shows up soon.
            cache.set(cache_key, snapshot, INBOX_SNAPSHOT_CACHE_TTL)
            return snapshot
    try:
        results = tagged(_read_list(account, mailbox, folder, limit), account)
    except InboxBusy as exc:
        health.record_failure(account, exc)
        exc.stale = cache.get(f"{INBOX_STALE_LIST_CACHE_PREFIX}{suffix}")
        if exc.stale is None and use_snapshot:
            exc.stale = health.last_snapshot(account, limit)
        raise
    except Exception as exc:
        health.record_failure(account, exc)
        raise
    # A live read of the snapshot's size (or larger) also refreshes the snapshot; a smaller one only the health.
    keeps_snapshot = use_snapshot and limit >= health.SNAPSHOT_LIMIT
    health.record_ok(account, messages=results[: health.SNAPSHOT_LIMIT] if keeps_snapshot else None)
    cache.set(cache_key, results, INBOX_LIST_CACHE_TTL)
    cache.set(f"{INBOX_STALE_LIST_CACHE_PREFIX}{suffix}", results, INBOX_STALE_LIST_CACHE_TTL)
    return results


def _read_list(account, mailbox: str | None, folder: str, limit: int) -> list[dict[str, Any]]:
    if account.is_graph:
        return graph_backend.list_messages(graph_backend.reader_for(account.address), folder=folder, limit=limit)
    try:
        import apps.mail.services.inbox as inbox_api

        with inbox_api._open_inbox(mailbox=mailbox, folder=folder, account=account) as client:
            # The site's own credential mail is never listed from Sent (``credential_mail``): left out of the search
            # and dropped if it still comes back, before the list is cached.
            fetched = client.fetch(list_search(folder), limit=limit, reverse=True, mark_seen=False, bulk=True)
            messages = shown(fetched, folder)
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to list inbox messages.")
        raise InboxError("Failed to load inbox messages.") from exc
    return [message_summary(message) for message in messages]
