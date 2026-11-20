"""Each inbox account's last connection outcome and Inbox snapshot (``InboxAccountState``), shared by every container.

* The poller (``polling``) and every live read record here whether the account could be read.
* An account that could not connect is hidden from the inbox (``hidden_keys``) until it connects again: the poller
  retries it every interval, the inbox's Refresh retries it at once, and so does a page view once
  ``UNREACHABLE_RETRY`` has passed (so a stopped worker never hides an account for good).
* The Inbox list is served from the poller's snapshot while it is fresh (``fresh_snapshot``), so opening the inbox
  connects to no mailbox at all.

Recording is best effort: a failure to write the state is logged and never changes what the inbox shows.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils import timezone

from .connection import InboxBusy

logger = logging.getLogger(__name__)

# The poller keeps this many of each Inbox's newest messages: every list size but the largest is served from it.
SNAPSHOT_LIMIT = 50
UNREACHABLE_RETRY = timedelta(minutes=10)
UNREACHABLE_DETAIL = "Could not connect to this mailbox. Check its settings and the server logs."
UNREAD_CACHE_KEY = "inbox:unread-total"
UNREAD_CACHE_TTL = 30


def poll_interval_seconds() -> int:
    """Seconds between two polls (``MAIL_INBOX_POLL_SECONDS``, default 180, at least 60); 0 or less disables it."""
    value = int(getattr(settings, "MAIL_INBOX_POLL_SECONDS", 180))
    return 0 if value <= 0 else max(60, value)


def snapshot_max_age() -> timedelta:
    """How old a snapshot may be and still be listed: two poll intervals and a minute (one missed poll is fine)."""
    interval = poll_interval_seconds() or 180
    return timedelta(seconds=2 * interval + 60)


def _model():
    from apps.mail.models import InboxAccountState

    return InboxAccountState


def same_mailbox(state, account) -> bool:
    """Whether ``state`` was recorded for the mailbox ``account`` reads now. An IMAP account's key is its row, so
    changing the row's username keeps the key but points at another mailbox: its old snapshot (whose IMAP UIDs mean
    nothing in the new mailbox) must never be shown or reused for it."""
    return str(state.address or "").strip().lower() == str(account.address or "").strip().lower()


def states_for(accounts) -> dict:
    """``{account key: InboxAccountState}`` for the accounts that have one, recorded for the mailbox each reads now."""
    by_key = {account.key: account for account in accounts}
    if not by_key:
        return {}
    try:
        with transaction.atomic():
            states = list(_model().objects.filter(account_key__in=list(by_key)))
        return {state.account_key: state for state in states if same_mailbox(state, by_key[state.account_key])}
    except DatabaseError:
        logger.exception("Could not load the inbox account states.")
        return {}


def hidden_keys(accounts, *, now=None) -> set[str]:
    """Keys of the accounts that could not connect recently: the inbox leaves them out."""
    now = now or timezone.now()
    unreachable = _model().Status.UNREACHABLE
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


def record_ok(account, *, messages: list | None = None, now=None) -> None:
    """The account was read. ``messages`` (its newest Inbox messages, newest first) replaces the snapshot."""
    now = now or timezone.now()
    model = _model()
    fields = {
        "address": account.address,
        "status": model.Status.OK,
        "detail": "",
        "checked_at": now,
        "connected_at": now,
        "consecutive_failures": 0,
    }
    if messages is not None:
        kept = list(messages)[:SNAPSHOT_LIMIT]
        fields.update(
            messages=kept,
            snapshot_at=now,
            unread_count=sum(1 for message in kept if not message.get("is_seen")),
        )
    _save(account, fields)


def record_failure(account, exc: BaseException, *, now=None) -> None:
    """The account could not be read: held back (``InboxBusy``) or unreachable (anything else, or a refused sign-in).
    The snapshot is kept, to be shown as last read."""
    model = _model()
    if isinstance(exc, InboxBusy) and not exc.refused:
        status, detail = model.Status.BUSY, str(exc)
    elif isinstance(exc, InboxBusy):
        status, detail = model.Status.UNREACHABLE, str(exc)
    else:
        status, detail = model.Status.UNREACHABLE, UNREACHABLE_DETAIL
    fields = {"status": status, "detail": detail[:255], "checked_at": now or timezone.now()}
    _save(account, fields, failed=True)


def mark_seen(account, uid: str) -> None:
    """An opened IMAP message is now read (opening it set ``\\Seen``): update the snapshot until the next poll."""
    try:
        with transaction.atomic():
            state = _model().objects.select_for_update().filter(account_key=account.key).first()
            if state is None:
                return
            changed = False
            for message in state.messages or []:
                if message.get("uid") == uid and not message.get("is_seen"):
                    message["is_seen"] = True
                    changed = True
            if changed:
                state.unread_count = sum(1 for message in state.messages if not message.get("is_seen"))
                state.save(update_fields=["messages", "unread_count", "updated_at"])
    except DatabaseError:
        logger.exception("Could not update the inbox snapshot of %s.", account.key)
    _forget_unread()


def reset(keys=None, *, prefix: str = "") -> None:
    """Forget whether accounts could connect (their configuration changed): they are shown and tried again."""
    model = _model()
    try:
        with transaction.atomic():
            queryset = model.objects.exclude(status=model.Status.UNKNOWN)
            if keys is not None:
                queryset = queryset.filter(account_key__in=list(keys))
            if prefix:
                queryset = queryset.filter(account_key__startswith=prefix)
            queryset.update(status=model.Status.UNKNOWN, detail="")
    except DatabaseError:
        logger.exception("Could not reset the inbox account states.")
    _forget_unread()


def prune(accounts) -> int:
    """Delete the states of accounts the inbox no longer reads (their snapshots hold mail summaries)."""
    keys = [account.key for account in accounts]
    deleted, _ = _model().objects.exclude(account_key__in=keys).delete()
    return deleted


def unread_total() -> int:
    """Unread Inbox messages across the accounts that connect (the sidebar badge), cached briefly per container."""
    cached = cache.get(UNREAD_CACHE_KEY)
    if cached is not None:
        return cached
    from .accounts import readable_accounts

    try:
        accounts = readable_accounts()
    except Exception:
        logger.exception("Could not list the inbox accounts for the unread count.")
        return 0
    model = _model()
    total = sum(
        state.unread_count
        for state in states_for(accounts).values()
        if state.status != model.Status.UNREACHABLE and state.snapshot_at is not None
    )
    cache.set(UNREAD_CACHE_KEY, total, UNREAD_CACHE_TTL)
    return total


def _save(account, fields: dict, *, failed: bool = False) -> None:
    """Write ``fields`` (and, when ``failed``, one more consecutive failure) to the account's state.

    Every write goes through here. A row recorded for another mailbox (an IMAP account's row now names another
    username: same key, other mail) first loses its snapshot and failure count, so nothing of the old mailbox is
    ever shown, counted or reused for the new one.
    """
    model = _model()
    try:
        with transaction.atomic():
            state = model.objects.select_for_update().filter(account_key=account.key).first()
            if state is None:
                state = model(account_key=account.key)
            elif not same_mailbox(state, account):
                state.messages, state.snapshot_at, state.unread_count = [], None, 0
                state.consecutive_failures = 0
                state.connected_at = None
            state.address = account.address
            for name, value in fields.items():
                setattr(state, name, value)
            if failed:
                state.consecutive_failures += 1
            state.save()
    except DatabaseError:
        logger.exception("Could not record the inbox state of %s.", account.key)
    _forget_unread()


def _forget_unread() -> None:
    cache.delete(UNREAD_CACHE_KEY)
