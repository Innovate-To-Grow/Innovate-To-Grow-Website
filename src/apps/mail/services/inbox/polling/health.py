"""Each inbox account's last connection outcome and Inbox snapshot (``InboxAccountState``), shared by every container.

* The poller (``poller``) and every live read record whether the account could be read (``records``; its functions
  are re-exported here, and callers use them through this module).
* An account that could not connect is hidden from the inbox (``hidden_keys``) until it connects again: the poller
  retries it every interval, the inbox's Refresh retries it at once, and so does a page view once
  ``UNREACHABLE_RETRY`` has passed (so a stopped worker never hides an account for good).
* The Inbox list is served from the poller's snapshot while it is fresh (``fresh_snapshot``), so opening the inbox
  connects to no mailbox at all.

Only a state recorded for the mailbox an account reads now is ever used (``records.same_mailbox``).
"""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils import timezone

from .records import (  # noqa: F401 - re-exported: callers record through this module
    SNAPSHOT_LIMIT,
    UNREACHABLE_DETAIL,
    UNREAD_CACHE_KEY,
    logger,
    mark_seen,
    prune,
    record_failure,
    record_ok,
    reset,
    same_mailbox,
    state_model,
)

UNREACHABLE_RETRY = timedelta(minutes=10)
UNREAD_CACHE_TTL = 30


def poll_interval_seconds() -> int:
    """Seconds between two polls (``MAIL_INBOX_POLL_SECONDS``, default 180, at least 60); 0 or less disables it."""
    value = int(getattr(settings, "MAIL_INBOX_POLL_SECONDS", 180))
    return 0 if value <= 0 else max(60, value)


def snapshot_max_age() -> timedelta:
    """How old a snapshot may be and still be listed: two poll intervals and a minute (one missed poll is fine)."""
    interval = poll_interval_seconds() or 180
    return timedelta(seconds=2 * interval + 60)


def states_for(accounts) -> dict:
    """``{account key: InboxAccountState}`` for the accounts that have one, recorded for the mailbox each reads now."""
    by_key = {account.key: account for account in accounts}
    if not by_key:
        return {}
    try:
        with transaction.atomic():
            states = list(state_model().objects.filter(account_key__in=list(by_key)))
        return {state.account_key: state for state in states if same_mailbox(state, by_key[state.account_key])}
    except DatabaseError:
        logger.exception("Could not load the inbox account states.")
        return {}


def hidden_keys(accounts, *, now=None) -> set[str]:
    """Keys of the accounts that could not connect recently: the inbox leaves them out."""
    now = now or timezone.now()
    unreachable = state_model().Status.UNREACHABLE
    return {
        key
        for key, state in states_for(accounts).items()
        if state.status == unreachable and state.checked_at and state.checked_at >= now - UNREACHABLE_RETRY
    }


def fresh_snapshot(account, limit: int, *, now=None) -> list | None:
    """The account's newest ``limit`` Inbox messages from the poller's snapshot, or None when there is none fresh
    enough (or ``limit`` is larger than the snapshot keeps)."""
    if limit > SNAPSHOT_LIMIT:
        return None
    state = states_for([account]).get(account.key)
    if state is None or state.snapshot_at is None or state.status == state.Status.UNREACHABLE:
        return None
    if state.snapshot_at < (now or timezone.now()) - snapshot_max_age():
        return None
    return list(state.messages or [])[:limit]


def last_snapshot(account, limit: int) -> list | None:
    """The last snapshot however old (shown, with a banner, while reads are held back), or None."""
    state = states_for([account]).get(account.key)
    if state is None or state.snapshot_at is None:
        return None
    return list(state.messages or [])[:limit]


def unread_total() -> int:
    """Unread Inbox messages across the accounts that connect (the sidebar badge), cached briefly per container."""
    cached = cache.get(UNREAD_CACHE_KEY)
    if cached is not None:
        return cached
    from ..reading.accounts import readable_accounts

    try:
        accounts = readable_accounts()
    except Exception:
        logger.exception("Could not list the inbox accounts for the unread count.")
        return 0
    unreachable = state_model().Status.UNREACHABLE
    total = sum(
        state.unread_count
        for state in states_for(accounts).values()
        if state.status != unreachable and state.snapshot_at is not None
    )
    cache.set(UNREAD_CACHE_KEY, total, UNREAD_CACHE_TTL)
    return total
