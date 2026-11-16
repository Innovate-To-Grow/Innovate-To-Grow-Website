"""The failure counters: the keys they are stored under (``ScopedKey``, the identifier digest), their windows, and
the row writes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from django.db import IntegrityError, router, transaction
from django.db.models import Q
from django.utils.crypto import salted_hmac

from apps.authn.models import LoginFailureWindow
from apps.authn.models.contact.phone_regions import PHONE_REGION_CHOICES

from ...contacts.contact_phones import normalize_to_national

# (label, window length in seconds, failures that lock the identifier). A window locks once its counter reaches the
# limit; the longer window is the backstop against an attacker who paces guesses just under the short one.
FAILURE_WINDOWS = (
    ("15m", 15 * 60, 10),
    ("24h", 24 * 60 * 60, 30),
)

_HASH_SALT = "login-guard.identifier"
# HMAC key salt of ScopedKey digests. It must stay different from _HASH_SALT: that difference is what keeps the two
# kinds of counters apart (see ScopedKey).
_SCOPE_HASH_SALT = "login-guard.scope"
_SCOPE_NAME = re.compile(r"[a-z][a-z0-9-]*")


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


def _raw_delete(queryset) -> int:
    """Delete ``queryset`` with one ``DELETE`` statement and return the row count.

    ``QuerySet.delete()`` is not that here: an installed app (django-ckeditor-5) connects a ``pre_delete`` receiver
    for every model, which turns each delete into a ``SELECT`` of the rows plus one ``DELETE`` per 100 of them.
    Nothing references a failure window and it has no delete signals of its own (a test pins both), so skipping the
    collector loses nothing.
    """
    return queryset._raw_delete(router.db_for_write(LoginFailureWindow))


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
