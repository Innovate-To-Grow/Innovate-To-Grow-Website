"""Locking an identifier out after repeated failures: checking, recording, clearing and purging its windows."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from django.db import transaction
from django.db.models import F

from apps.authn.models import LoginFailureWindow

from .counters import (
    FAILURE_WINDOWS,
    ScopedKey,
    _current_windows,
    _digest,
    _insert_window,
    _raw_delete,
    _window,
    normalize_identifier,
)

# These functions used to live in ``login_guard`` itself; keep that logger name.
logger = logging.getLogger("apps.authn.services.login_guard")


# Site-wide failures per 5-minute window at which one WARNING is logged. Detection only: nothing is ever refused, so
# a false alarm costs one log line and never locks the campus out. 200 per 5 minutes is two-thirds of a failure every
# second, sustained, which honest traffic here does not approach: it only counts wrong passwords and unknown
# identifiers that reached the credential check (not locked or malformed requests), and even a sign-in rush where
# every one of a few thousand members typed a wrong password once would spread over far more than five minutes. A
# spray that covers a member list at any useful speed crosses it within its first window. Tune it against the
# observed baseline once the metric filter has some history.
SPRAY_WINDOW = ("5m", 5 * 60)
SPRAY_ALERT_THRESHOLD = 200

# Rows deleted per statement by purge_expired_failure_windows.
PURGE_BATCH_SIZE = 1000

LOCKED_DETAIL = "Too many failed sign-in attempts. Please try again later or sign in with an email code."
LOCKED_CODE = "login_locked"

# UPDATE-then-INSERT rounds before giving up on counting one failure. Two suffice unless a concurrent successful
# sign-in keeps deleting the row in between, and then that success has cleared the count anyway.
_INCREMENT_ATTEMPTS = 3


class LoginLocked(Exception):
    """The identifier has too many recent failures; ``retry_after`` is the seconds until the lock lifts."""

    def __init__(self, retry_after: int):
        super().__init__(LOCKED_DETAIL)
        self.retry_after = retry_after


def _identifier_digest(identifier) -> str | None:
    if isinstance(identifier, ScopedKey):
        return identifier.digest()
    normalised = normalize_identifier(identifier)
    return _digest(normalised) if normalised else None


def retry_after(identifier) -> int:
    """Seconds until ``identifier`` may try a password again, or ``0`` when it is not locked."""
    digest = _identifier_digest(identifier)
    if digest is None:
        return 0
    windows, current = _current_windows(time.time())
    counts = dict(
        LoginFailureWindow.objects.filter(current, identifier_digest=digest).values_list("window", "failure_count")
    )
    return max(
        (remaining for (label, _index, remaining, _end), limit in windows if counts.get(label, 0) >= limit),
        default=0,
    )


def ensure_not_locked(identifier) -> None:
    """Raise ``LoginLocked`` when ``identifier`` is locked. Call this before any password work."""
    wait = retry_after(identifier)
    if wait:
        raise LoginLocked(wait)


def record_failure(identifier) -> None:
    """Count one credential failure against ``identifier`` and the spray detector (no-op for a blank identifier).

    Each window's count is committed on its own, so do not call this inside a transaction that may roll back.
    """
    digest = _identifier_digest(identifier)
    if digest is None:
        return
    now = time.time()
    for label, length, limit in FAILURE_WINDOWS:
        label, index, _remaining, end = _window(label, length, now)
        if _increment(digest, label, index, end) == limit:
            logger.warning("Password sign-in locked: window=%s identifier_hash=%s", label, digest[:12])
    label, index, _remaining, end = _window(*SPRAY_WINDOW, now)
    if _increment(LoginFailureWindow.GLOBAL_DIGEST, label, index, end) == SPRAY_ALERT_THRESHOLD:
        logger.warning(
            "login_guard.failure_spike failures=%d window=%s threshold=%d",
            SPRAY_ALERT_THRESHOLD,
            label,
            SPRAY_ALERT_THRESHOLD,
        )


def clear(identifier) -> None:
    """Forget ``identifier``'s failures (after a successful sign-in). The site-wide spray count is kept.

    Only the rows of the windows that hold "now" are deleted: exactly the rows ``retry_after`` reads, so nothing that
    could still lock the identifier survives. Rows of windows that have ended no longer count and are left to
    ``purge_expired_failure_windows``. That keeps the two deletes on different rows (the purge only takes ended
    windows), so they do not lock the same rows in opposite orders and deadlock a sign-in. The one overlap left
    needs both of the identifier's windows to end between this function reading the clock and its ``DELETE`` running,
    which only happens at UTC midnight, with the purge starting in that same instant.
    """
    digest = _identifier_digest(identifier)
    if digest is not None:
        _windows, current = _current_windows(time.time())
        _raw_delete(LoginFailureWindow.objects.filter(current, identifier_digest=digest))


def purge_expired_failure_windows(
    now: datetime | None = None,
    batch_size: int = PURGE_BATCH_SIZE,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """Delete the rows of windows that ended at or before ``now``, ``batch_size`` rows per statement.

    Returns the number of rows deleted. Only ended windows are touched, so running this never unlocks anyone early.
    Each batch is one ``DELETE`` committed on its own. ``should_stop`` is asked before every batch: once it returns
    true the purge returns what it has deleted so far and the next run carries on.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    cutoff = now or datetime.fromtimestamp(time.time(), tz=UTC)
    expired = LoginFailureWindow.objects.filter(expires_at__lte=cutoff)
    total = 0
    while not (should_stop is not None and should_stop()):
        batch = list(expired.order_by("expires_at").values_list("pk", flat=True)[:batch_size])
        if not batch:
            break
        total += _raw_delete(expired.filter(pk__in=batch))
        if len(batch) < batch_size:
            break
    return total


def _increment(digest: str, label: str, index: int, expires_at: datetime) -> int:
    """Add one failure to the ``(digest, label, index)`` row and return its new count (``0`` if it could not).

    The ``UPDATE`` is atomic in the database, so concurrent increments never lose a failure, and the transaction
    keeps the row locked until the count is read back, so exactly one caller sees each value (the threshold logs
    fire once). When the window has no row yet the first failure inserts it; a worker that loses that insert race to
    another gets an ``IntegrityError`` from the unique constraint and counts on top of the winner's row instead.
    """
    rows = LoginFailureWindow.objects.filter(identifier_digest=digest, window=label, window_index=index)
    with transaction.atomic():
        for _attempt in range(_INCREMENT_ATTEMPTS):
            if rows.update(failure_count=F("failure_count") + 1):
                return rows.values_list("failure_count", flat=True).get()
            if _insert_window(digest, label, index, expires_at):
                return 1
    return 0
