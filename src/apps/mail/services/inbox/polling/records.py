"""Writing each inbox account's state (``InboxAccountState``): whether a read connected, and its Inbox snapshot.

The poller (``poller``) and every live read (``reading.listing``) record here; ``health`` reads it back and
re-exports these functions, which callers use through it. Recording is best effort: a failure to write is logged and
never changes what the inbox shows.
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils import timezone

from ..reading.connection import InboxBusy

# One logger for the account state, read and written (``health``).
logger = logging.getLogger("apps.mail.services.inbox.polling.health")

# The poller keeps this many of each Inbox's newest messages: every list size but the largest is served from it.
SNAPSHOT_LIMIT = 50
UNREACHABLE_DETAIL = "Could not connect to this mailbox. Check its settings and the server logs."
UNREAD_CACHE_KEY = "inbox:unread-total"


# ``{account key: InboxAccountState or None}`` loaded during one inbox request (``request_scope``), else None.
_SCOPE: ContextVar[dict | None] = ContextVar("inbox_account_states", default=None)


@contextmanager
def request_scope():
    """While the block runs (one inbox fragment request), each account's state is loaded from the database at most
    once (``health.states_for``), and what this request records replaces it (``_save``), so the request still sees
    whether each account connected just now."""
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def scoped_states() -> dict | None:
    return _SCOPE.get()


def forget_scope() -> None:
    memo = _SCOPE.get()
    if memo is not None:
        memo.clear()


def state_model():
    from apps.mail.models import InboxAccountState

    return InboxAccountState


def same_mailbox(state, account) -> bool:
    """Whether ``state`` was recorded for the mailbox ``account`` reads now. An IMAP account's key is its row, so
    changing the row's username keeps the key but points at another mailbox: its old snapshot (whose IMAP UIDs mean
    nothing in the new mailbox) must never be shown or reused for it."""
    return str(state.address or "").strip().lower() == str(account.address or "").strip().lower()


def record_ok(account, *, messages: list | None = None, now=None) -> None:
    """The account was read. ``messages`` (its newest Inbox messages, newest first) replaces the snapshot."""
    now = now or timezone.now()
    model = state_model()
    fields = {
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
    model = state_model()
    if isinstance(exc, InboxBusy) and not exc.refused:
        status, detail = model.Status.BUSY, str(exc)
    elif isinstance(exc, InboxBusy):
        status, detail = model.Status.UNREACHABLE, str(exc)
    else:
        status, detail = model.Status.UNREACHABLE, UNREACHABLE_DETAIL
    fields = {"status": status, "detail": detail[:255], "checked_at": now or timezone.now()}
    _save(account, fields, failed=True)


def reset(keys=None, *, prefix: str = "") -> None:
    """Forget whether accounts could connect (their configuration changed): they are shown and tried again."""
    model = state_model()
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
    forget_scope()
    forget_unread()


def prune(accounts) -> int:
    """Delete the states of accounts the inbox no longer reads (their snapshots hold mail summaries)."""
    keys = [account.key for account in accounts]
    deleted, _ = state_model().objects.exclude(account_key__in=keys).delete()
    return deleted


def forget_unread() -> None:
    cache.delete(UNREAD_CACHE_KEY)


def _save(account, fields: dict, *, failed: bool = False) -> None:
    """Write ``fields`` (and, when ``failed``, one more consecutive failure) to the account's state.

    Every write goes through here. A row recorded for another mailbox (an IMAP account's row now names another
    username: same key, other mail) first loses its snapshot and failure count, so nothing of the old mailbox is
    ever shown, counted or reused for the new one.
    """
    model = state_model()
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
        forget_scope()
    else:
        memo = _SCOPE.get()
        if memo is not None:
            memo[account.key] = state
    forget_unread()
