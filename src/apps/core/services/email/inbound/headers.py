"""Reading an inbound message's headers safely, for the classifier and the apps that store inbound mail.

Anyone can mail the mailbox, so the input is hostile: messages are parsed with the ``compat32`` policy (headers stay
plain strings until read), at most ``MAX_HEADERS`` headers are kept, and every value is cut to 998 characters
(RFC 5322's line limit; ``References`` and address lists get a few lines more) before it is decoded or parsed, so the
work stays linear in the input, as in the bounce report parser. NUL characters are dropped: PostgreSQL text cannot
hold them, so a Message-ID carrying one would make the message impossible to store.
"""

import email
import email.policy
import re
from datetime import UTC, datetime
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime

from ..telemetry import text

LIMIT = text.HEADER_LIMIT
MAX_HEADERS = 200
MAX_ADDRESSES = 100
MAX_MESSAGE_IDS = 50
_LONG_LIMIT = 16 * LIMIT
_LONG_HEADERS = ("references", "to", "cc", "authentication-results", "x-forefront-antispam-report")
_MESSAGE_ID_RE = re.compile(r"<[^<>\s]{1,250}>")


def parse(raw: bytes):
    """The message in ``raw`` (``compat32``: nothing is decoded until it is read)."""
    return email.message_from_bytes(raw, policy=email.policy.compat32)


def header_map(message) -> dict[str, list[str]]:
    """Lower-case header name → its raw values, in order, for the first ``MAX_HEADERS`` headers."""
    headers: dict[str, list[str]] = {}
    for name, value in message.items()[:MAX_HEADERS]:
        key = str(name).strip().lower()[:100]
        limit = _LONG_LIMIT if key in _LONG_HEADERS else LIMIT
        headers.setdefault(key, []).append(str(value)[:limit].replace("\x00", ""))
    return headers


def first(headers: dict[str, list[str]], name: str) -> str:
    values = headers.get(name.lower())
    return values[0] if values else ""


def joined(headers: dict[str, list[str]], name: str) -> str:
    return "\n".join(headers.get(name.lower(), ()))


def decoded(value) -> str:
    """A header value with its encoded words decoded (``=?utf-8?q?...?=``), single-line and cleaned."""
    raw = str(value or "")[:LIMIT]
    try:
        result = str(make_header(decode_header(raw)))
    except (HeaderParseError, LookupError, UnicodeError, ValueError):
        result = raw
    return text.clean(result, LIMIT)


def addresses(value, limit: int = MAX_ADDRESSES) -> list[tuple[str, str]]:
    """``(display name, bare lower-case address)`` pairs of an address header, at most ``limit``, valid ones only."""
    pairs = []
    try:
        parsed = getaddresses([str(value or "")[:_LONG_LIMIT]])
    except (HeaderParseError, IndexError, TypeError, ValueError):
        return []
    for name, addr in parsed:
        bare = text.address(addr)
        if bare:
            pairs.append((decoded(name)[:255], bare))
        if len(pairs) >= limit:
            break
    return pairs


def message_ids(value, limit: int = MAX_MESSAGE_IDS) -> list[str]:
    """The ``<...>`` Message-IDs in a header, in order, unique, at most the last ``limit`` (a long References chain
    keeps its most recent ids, which name the messages a reply is closest to)."""
    found = list(dict.fromkeys(_MESSAGE_ID_RE.findall(str(value or "")[:_LONG_LIMIT])))
    return found[-limit:]


def date(value) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(str(value)[:LIMIT]) if value else None
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def content_type(message) -> tuple[str, dict[str, str]]:
    """The top-level content type (lower-case) and its parameters (lower-case names, values cut)."""
    try:
        main = message.get_content_type()
        params = {str(k).lower(): str(v)[:100] for k, v in (message.get_params() or [])[1:20]}
    except (HeaderParseError, IndexError, TypeError, ValueError):
        return "text/plain", {}
    return main, params
