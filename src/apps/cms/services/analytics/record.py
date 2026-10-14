"""Bound every client-controlled field of a page view before it is buffered.

Page views are written with one ``bulk_create`` per batch, so a single value the database refuses loses the whole
batch, every other visitor's rows included. PostgreSQL refuses a string longer than its ``varchar`` column, a NUL
character, an index entry that is too large and a malformed ``inet``; SQLite (local development) accepts all of
them, so nothing here can be left to the database. ``user_agent`` is a ``TextField`` with no limit at all, so it is
cut here as well: one request must not be able to store kilobytes of header.

The API rejects a ``path`` or ``referrer`` longer than its column with a 400 before this runs (the serializer
validates the size). Request metadata the visitor did not type cannot be "rejected", so it is cut or dropped
instead: the user agent is truncated, and a session cookie or client address that cannot be a real one is stored
as empty.
"""

import ipaddress

from .visitor import clean_visitor_id

PATH_MAX_LENGTH = 2048
REFERRER_MAX_LENGTH = 2048
USER_AGENT_MAX_LENGTH = 512
SESSION_KEY_MAX_LENGTH = 64

# ``path`` is indexed (alone and with the timestamp), and PostgreSQL refuses a B-tree entry of more than about
# 2,700 bytes. 2,048 characters of non-ASCII text are up to 8 kB of UTF-8, so the path is bounded in bytes too.
# Real paths are percent-encoded ASCII, for which the two limits are the same.
PATH_MAX_BYTES = 2048


def _clip(value, limit: int, max_bytes: int | None = None) -> str:
    """``value`` as storable text of at most ``limit`` characters (and ``max_bytes`` of UTF-8).

    "" when it is not a string. NUL characters and lone surrogates are removed: no PostgreSQL text column takes
    either.
    """
    if not isinstance(value, str):
        return ""
    encoded = value.replace("\x00", "")[:limit].encode("utf-8", "ignore")  # "ignore" drops lone surrogates
    if max_bytes is not None:
        encoded = encoded[:max_bytes]
    return encoded.decode("utf-8", "ignore")  # "ignore" drops a character the byte limit cut in half


def clean_session_key(value) -> str:
    """The session key when it can be stored as one, else "".

    The value is whatever the session cookie holds, which the client controls. A real Django session key is 32
    characters; a longer value is junk, and half of a key identifies nothing, so it is dropped rather than cut.
    """
    if isinstance(value, str) and _clip(value, SESSION_KEY_MAX_LENGTH) == value:  # fits, and storable as it is
        return value
    return ""


def clean_ip_address(value) -> str | None:
    """``value`` as a canonical IPv4 / IPv6 address, or ``None`` when it is not one.

    Without trusted-proxy configuration the address is the first ``X-Forwarded-For`` entry, which the client
    writes: it may be any text.
    """
    if not isinstance(value, str):
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if getattr(address, "scope_id", None):  # "fe80::1%eth0": valid for Python, not for an inet column
        return None
    return str(address)


def bounded_page_view(data: dict) -> dict:
    """A copy of ``data`` in which every client-controlled field present fits its column."""
    bounded = dict(data)
    if "path" in bounded:
        bounded["path"] = _clip(bounded["path"], PATH_MAX_LENGTH, PATH_MAX_BYTES)
    if "referrer" in bounded:
        bounded["referrer"] = _clip(bounded["referrer"], REFERRER_MAX_LENGTH)
    if "user_agent" in bounded:
        bounded["user_agent"] = _clip(bounded["user_agent"], USER_AGENT_MAX_LENGTH)
    if "session_key" in bounded:
        bounded["session_key"] = clean_session_key(bounded["session_key"])
    if "ip_address" in bounded:
        bounded["ip_address"] = clean_ip_address(bounded["ip_address"])
    if "visitor_id" in bounded:
        bounded["visitor_id"] = clean_visitor_id(bounded["visitor_id"])
    return bounded
