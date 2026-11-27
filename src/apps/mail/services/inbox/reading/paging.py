"""The inbox list's "Load older" cursor: where each account's next page starts.

A cursor holds one position per account key:

* ``u<uid>``: a Gmail IMAP account continues below that UID (UIDs only grow, so new mail never shifts the page);
* ``s<n>``: a Microsoft Graph account skips its newest ``n`` messages (``$skip``);
* ``x``: the account has nothing older.

An account the cursor does not name starts from its newest message. In the browser the cursor is an opaque
URL-safe token (``encode``); ``decode`` accepts only well-formed positions, so a hand-written token can at worst
page an account the request may already read.
"""

import base64
import binascii
import json
import re
from dataclasses import dataclass

EXHAUSTED = "x"
MAX_TOKEN_LENGTH = 4096
MAX_ACCOUNTS = 50
_POSITION = re.compile(r"(?:u[1-9][0-9]{0,11}|s[0-9]{1,6}|x)")


@dataclass(frozen=True)
class Position:
    """Where one account's page starts: below IMAP UID ``before`` or after Graph's newest ``skip``."""

    before: int | None = None
    skip: int = 0

    @property
    def is_start(self) -> bool:
        return self.before is None and not self.skip

    @property
    def key(self) -> str:
        """Part of the account's list cache key (empty for the first page, whose cache key never changed)."""
        if self.before is not None:
            return f"u{self.before}"
        return f"s{self.skip}" if self.skip else ""


START = Position()


def decode(token: str | None) -> dict[str, str]:
    """``{account key: position}`` from a token; ``{}`` (every account from its newest) for anything malformed."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return {}
    try:
        raw = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return {}
    if not isinstance(raw, dict) or len(raw) > MAX_ACCOUNTS:
        return {}
    return {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and 0 < len(key) <= 300 and isinstance(value, str) and _POSITION.fullmatch(value)
    }


def encode(cursor: dict[str, str]) -> str:
    data = json.dumps(cursor, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def position(cursor: dict[str, str], account) -> Position | None:
    """``account``'s page start, or None when it has nothing older. A position of the other provider's kind (the
    key now names another kind of account) starts over."""
    value = cursor.get(account.key, "")
    if value == EXHAUSTED:
        return None
    if value.startswith("u") and not account.is_graph:
        return Position(before=int(value[1:]))
    if value.startswith("s") and account.is_graph:
        return Position(skip=int(value[1:]))
    return START


def advance(cursor: dict[str, str], account, start: Position, read: list[dict], shown: list[dict], limit: int) -> None:
    """Move ``account`` in ``cursor`` past a page: ``read`` is what its read returned (newest first), ``shown`` the
    part of it the page kept (a merged page keeps only the newest ``limit`` of every account together)."""
    value = _next(cursor.get(account.key, ""), account, start, read, shown, limit)
    if value:
        cursor[account.key] = value
    else:
        cursor.pop(account.key, None)


def _next(current: str, account, start: Position, read: list[dict], shown: list[dict], limit: int) -> str:
    if len(shown) >= len(read) and len(read) < limit:
        return EXHAUSTED
    if account.is_graph:
        return f"s{start.skip + len(shown)}"
    if shown:
        return f"u{min(_uids(shown))}" if _uids(shown) else current
    # Nothing of it was kept (newer mail of other accounts filled the page): it starts at its newest read again.
    return current or (f"u{max(_uids(read)) + 1}" if _uids(read) else "")


def _uids(messages: list[dict]) -> list[int]:
    return [int(message["uid"]) for message in messages if str(message.get("uid", "")).isdigit()]


def has_more(cursor: dict[str, str]) -> bool:
    return any(value != EXHAUSTED for value in cursor.values())
