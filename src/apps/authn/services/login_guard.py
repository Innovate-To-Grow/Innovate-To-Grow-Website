"""Failure lockout for password sign-in, keyed on the submitted identifier (never on the client IP).

Why the identifier: most users share the campus public IP, so a per-IP limit throttles everyone at once while an
attacker rotating ``X-Forwarded-For`` values barely notices it. Guessing is instead bounded per account: once an
identifier has ``FAILURE_WINDOWS`` failures in a window it is refused (HTTP 429, ``login_locked``) until that window
ends. The client IP plays no role anywhere in this module.

Rules the callers rely on:

* Only credential failures count (unknown, inactive or unverified identifier, wrong password), and they count the
  same for every identifier, so neither the count nor the lockout reveals whether an account exists. Malformed
  requests (missing fields, undecryptable password) never count.
* The lockout is checked *before* the RSA decrypt and the PBKDF2 ``check_password``, so a locked identifier costs the
  server one indexed ``SELECT`` and no password work; a correct password does not bypass it. A successful sign-in
  clears the identifier's counters.
* Different identifiers are independent. The same phone number written in different formats, or the same email in a
  different case, is one identifier. A member with several verified emails plus a phone has one budget per
  identifier; the lockout cannot be keyed on the member without becoming an enumeration oracle.
* Identifiers are never stored: rows carry a SECRET_KEY-salted HMAC of the normalised identifier.
* A counter that must not be reachable by typing an identifier anywhere uses a ``ScopedKey`` instead of an
  identifier (the remembered-admin form does: whoever knows a staff address can fail the public login for it, and
  that must not lock the form only the holder of the signed cookie can post). Every function here that takes an
  identifier takes a ``ScopedKey`` too, with the same windows, limits, storage and spray counting.

Counters live in PostgreSQL (``LoginFailureWindow``), one row per identifier and clock-aligned window, so every
worker and every ECS task shares them, nothing evicts them and ``Retry-After`` is exact. Production has no Redis and
its file cache is per task, which is why they are not in the Django cache. A failure is one
``UPDATE ... SET failure_count = failure_count + 1`` (inserting the row when the window has none, tolerant of two
workers inserting it at once), so concurrent failures are never lost; each window can be overshot by at most one
attempt per request already past the check. A successful sign-in deletes the identifier's current rows only; rows of
ended windows are removed by ``purge_expired_failure_windows``.
Database errors are not caught: they fail the request.

Password spraying (one password tried against many identifiers) stays under every per-identifier limit, and blocking
it globally would lock the whole campus out at once. It is *detected* instead: every counted failure also increments
one site-wide row per ``SPRAY_WINDOW``, and the failure that reaches ``SPRAY_ALERT_THRESHOLD`` logs a single
``login_guard.failure_spike`` WARNING (counts only) for a CloudWatch Logs metric filter and alarm. Nothing is refused.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from django.db import IntegrityError, router, transaction
from django.db.models import F, Q
from django.utils.crypto import salted_hmac

from apps.authn.models import LoginFailureWindow
from apps.authn.models.contact.phone_regions import PHONE_REGION_CHOICES

from .contacts.contact_phones import normalize_to_national

logger = logging.getLogger(__name__)

# (label, window length in seconds, failures that lock the identifier). A window locks once its counter reaches the
# limit; the longer window is the backstop against an attacker who paces guesses just under the short one.
FAILURE_WINDOWS = (
    ("15m", 15 * 60, 10),
    ("24h", 24 * 60 * 60, 30),
)

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

_HASH_SALT = "login-guard.identifier"
# HMAC key salt of ScopedKey digests. It must stay different from _HASH_SALT: that difference is what keeps the two
# kinds of counters apart (see ScopedKey).
_SCOPE_HASH_SALT = "login-guard.scope"
_SCOPE_NAME = re.compile(r"[a-z][a-z0-9-]*")

# UPDATE-then-INSERT rounds before giving up on counting one failure. Two suffice unless a concurrent successful
# sign-in keeps deleting the row in between, and then that success has cleared the count anyway.
_INCREMENT_ATTEMPTS = 3


class LoginLocked(Exception):
    """The identifier has too many recent failures; ``retry_after`` is the seconds until the lock lifts."""

    def __init__(self, retry_after: int):
        super().__init__(LOCKED_DETAIL)
        self.retry_after = retry_after


@dataclass(frozen=True)
class ScopedKey:
    """A counter chosen by server code, in a namespace no submitted identifier can reach.

    ``scope`` names the caller's namespace (lower-case letters, digits and hyphens: no colon, so ``scope`` and
    ``subject`` cannot run into each other) and ``subject`` is whatever that caller counts per, for example a member
    id it took from a signed cookie. Pass the key wherever this module takes an identifier.

    Why typed input can never land on a scoped counter, whatever is typed and on whichever endpoint:

    * a request body yields strings and numbers, never a ``ScopedKey``; those always go through
      ``normalize_identifier`` and are hashed under ``_HASH_SALT``;
    * a ``ScopedKey`` is hashed under ``_SCOPE_HASH_SALT``. ``salted_hmac`` derives the HMAC key from the salt, so the
      two kinds are digests under different keys: even if ``normalize_identifier`` returned the very text of a
      scoped key (it cannot today: it only emits ``email:``, ``phone:`` and ``other:`` strings), the row would be a
      different one.

    Unlike a blank identifier, which is silently never counted, a malformed key is a programming error and raises
    ``ValueError``: a counter that silently did nothing would leave its form unbounded.
    """

    scope: str
    subject: str

    def __post_init__(self):
        if not isinstance(self.scope, str) or not _SCOPE_NAME.fullmatch(self.scope):
            raise ValueError("ScopedKey.scope must be lower-case letters, digits and hyphens, starting with a letter.")
        if not isinstance(self.subject, str) or not self.subject or self.subject != self.subject.strip():
            raise ValueError("ScopedKey.subject must be a non-empty string without surrounding whitespace.")

    def digest(self) -> str:
        return salted_hmac(_SCOPE_HASH_SALT, f"{self.scope}:{self.subject}", algorithm="sha256").hexdigest()


def normalize_identifier(identifier) -> str:
    """Canonical form of a submitted sign-in identifier, or ``""`` when there is none.

    Follows ``resolve_login_identifier``: an ``@`` makes it an email (trimmed and case-folded); otherwise anything
    holding a digit is a phone number and reduces to its national digits, so ``+1 (209) 555-1234``,
    ``12095551234`` and ``2095551234`` are one identifier. Email case-folding goes through ``upper().lower()``
    because the database matches emails case-insensitively through ``UPPER()``, which also equates look-alikes such
    as ``ſ`` with ``s`` and ``ı`` with ``i``; folding them here stops them from minting fresh budgets for one account.
    """
    text = str(identifier or "").strip()
    if not text:
        return ""
    if "@" in text:
        return f"email:{text.upper().lower()}"
    if re.search(r"\d", text):
        # The resolver (resolve_login_identifier) tries every region in PHONE_REGION_CHOICES; this key uses the first.
        # That is the same thing while there is a single region (pinned by a test): revisit both when one is added.
        return f"phone:{normalize_to_national(text, PHONE_REGION_CHOICES[0][0])}"
    return f"other:{text.upper().lower()}"


def _digest(normalised: str) -> str:
    return salted_hmac(_HASH_SALT, normalised, algorithm="sha256").hexdigest()


def _identifier_digest(identifier) -> str | None:
    if isinstance(identifier, ScopedKey):
        return identifier.digest()
    normalised = normalize_identifier(identifier)
    return _digest(normalised) if normalised else None


def _window(label: str, length: int, now: float) -> tuple[str, int, int, datetime]:
    """``(label, window index, seconds left in the window, end of the window)`` for the window holding ``now``."""
    index = int(now // length)
    end = (index + 1) * length
    return label, index, max(1, math.ceil(end - now)), datetime.fromtimestamp(end, tz=UTC)


def _current_windows(now: float) -> tuple[list, Q]:
    """The windows of ``FAILURE_WINDOWS`` that hold ``now`` (each with its limit), and the filter matching their rows."""
    windows = [(_window(label, length, now), limit) for label, length, limit in FAILURE_WINDOWS]
    current = Q()
    for (label, index, _remaining, _end), _limit in windows:
        current |= Q(window=label, window_index=index)
    return windows, current


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


def _raw_delete(queryset) -> int:
    """Delete ``queryset`` with one ``DELETE`` statement and return the row count.

    ``QuerySet.delete()`` is not that here: an installed app (django-ckeditor-5) connects a ``pre_delete`` receiver
    for every model, which turns each delete into a ``SELECT`` of the rows plus one ``DELETE`` per 100 of them.
    Nothing references a failure window and it has no delete signals of its own (a test pins both), so skipping the
    collector loses nothing.
    """
    return queryset._raw_delete(router.db_for_write(LoginFailureWindow))


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


def _insert_window(digest: str, label: str, index: int, expires_at: datetime) -> bool:
    """Create the window's row holding its first failure; ``False`` when another worker created it first."""
    try:
        with transaction.atomic():  # a savepoint: losing the race must not break the enclosing transaction
            LoginFailureWindow.objects.create(
                identifier_digest=digest,
                window=label,
                window_index=index,
                failure_count=1,
                expires_at=expires_at,
            )
    except IntegrityError:
        return False
    return True
