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

The lockout itself is in ``guard``; the keys, windows and row writes it counts in are in ``counters``.
"""

from .counters import FAILURE_WINDOWS, ScopedKey, normalize_identifier
from .guard import (
    LOCKED_CODE,
    LOCKED_DETAIL,
    PURGE_BATCH_SIZE,
    SPRAY_ALERT_THRESHOLD,
    SPRAY_WINDOW,
    LoginLocked,
    clear,
    ensure_not_locked,
    purge_expired_failure_windows,
    record_failure,
    retry_after,
)

__all__ = [
    "FAILURE_WINDOWS",
    "LOCKED_CODE",
    "LOCKED_DETAIL",
    "PURGE_BATCH_SIZE",
    "SPRAY_ALERT_THRESHOLD",
    "SPRAY_WINDOW",
    "LoginLocked",
    "ScopedKey",
    "clear",
    "ensure_not_locked",
    "normalize_identifier",
    "purge_expired_failure_windows",
    "record_failure",
    "retry_after",
]
