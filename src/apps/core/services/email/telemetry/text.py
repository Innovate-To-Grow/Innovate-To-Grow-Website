"""Normalising and bounding what telemetry stores: addresses, subjects, Message-IDs and error texts.

Error texts come from the site's own classified exceptions, which never carry a response body or a token; they are
still scrubbed of anything shaped like a bearer token or a long base64 run before they are stored.
"""

import hashlib
import re
import unicodedata
from email.utils import parseaddr

_BEARER_RE = re.compile(r"(?i)bearer\s+\S+")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_.-]{60,}")
_SPACE_RE = re.compile(r"\s+")
_MESSAGE_ID_RE = re.compile(r"<[^<>\s]{1,250}>")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# RFC 5322's line limit: a longer value (only a hostile one) is cut before it is parsed, so parsing stays cheap.
HEADER_LIMIT = 998


def address(value) -> str:
    """The bare, lower-case address of ``value`` (a plain address or ``Name <address>``), or ""."""
    _name, addr = parseaddr(str(value or "")[:HEADER_LIMIT])
    addr = addr.strip().lower()
    return addr if "@" in addr and not _CONTROL_RE.search(addr) else ""


def addresses(values) -> list[str]:
    """Unique bare addresses, in order."""
    return list(dict.fromkeys(item for item in (address(value) for value in values) if item))


def normalize_subject(subject) -> str:
    """Case-folded, NFC, whitespace-collapsed: header folding and case changes do not count as differences."""
    text = unicodedata.normalize("NFC", str(subject or ""))
    return _SPACE_RE.sub(" ", text).strip().casefold()


def subject_digest(subject) -> str:
    """SHA-256 of the normalised subject ("" for an empty one); bounce matching compares these."""
    normalized = normalize_subject(subject)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def message_id(value) -> str:
    """A Message-ID in its ``<...>`` form, or "" when ``value`` holds none."""
    match = _MESSAGE_ID_RE.search(str(value or "")[:HEADER_LIMIT])
    return match.group(0) if match else ""


def clean(value, limit: int) -> str:
    """Printable, single-line, whitespace-collapsed text of at most ``limit`` characters (undecodable bytes of a
    hostile header, kept as lone surrogates by the email parser, become "?": the database could not store them)."""
    text = _CONTROL_RE.sub(" ", str(value or "").encode("utf-8", "replace").decode("utf-8"))
    return _SPACE_RE.sub(" ", text).strip()[:limit]


def scrub(value, limit: int = 500) -> str:
    """``clean`` with bearer tokens and long token-like runs replaced, for error texts."""
    text = _BEARER_RE.sub("[redacted]", str(value or ""))
    return clean(_LONG_TOKEN_RE.sub("[redacted]", text), limit)
