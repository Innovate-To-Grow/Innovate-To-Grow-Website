"""Removing personal sign-in links from inbound mail before anything of it is stored.

People reply quoting a blast, and the quote carries their personal links: ``/login-link#token=…`` (and the legacy
``/magic-login``), ``/impersonate-login#token=…``, one-click ``unsubscribe/<token>/`` and ``resubscribe/<token>/``,
the retired ``/unsubscribe-login``, or any link with a ``token=`` (or ``…_token=``) parameter. Each such URL, also
when it is percent-encoded inside another one (a "safe links" wrapper), is replaced as a whole by
``LINK_PLACEHOLDER``, and any remaining token-shaped run (60+ base64-ish characters, as ``telemetry.text`` scrubs
error texts) by ``REDACTED_PLACEHOLDER``. The functions work on plain text and on serialized HTML alike (attribute
values are quoted, and ``&amp;`` is matched like ``&``).
"""

import re
from urllib.parse import unquote

from ..telemetry import text

LINK_PLACEHOLDER = "[sign-in link removed]"
REDACTED_PLACEHOLDER = "[redacted]"

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s\"'<>]+")
_SENSITIVE_PATH_RE = re.compile(
    r"(?i)/(?:login-link|magic-login|impersonate-login|unsubscribe-login)(?:[/?#]|$)|/(?:un|re)subscribe/[^/?#\s]{8,}"
)
_TOKEN_PARAM_RE = re.compile(r"(?i)[?#&;][a-z_]{0,32}token=")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_.-]{60,}")
# A link can be wrapped (percent-encoded) more than once; a few rounds of decoding find any such inner link.
_DECODE_ROUNDS = 3


def is_sensitive_url(url: str) -> bool:
    """Whether ``url`` (or a link percent-encoded inside it) is a personal sign-in or subscription link."""
    candidate = str(url or "")
    for _round in range(_DECODE_ROUNDS + 1):
        if _SENSITIVE_PATH_RE.search(candidate) or _TOKEN_PARAM_RE.search(candidate):
            return True
        decoded = unquote(candidate)
        if decoded == candidate:
            return False
        candidate = decoded
    return False


def _replace(match: re.Match) -> str:
    return LINK_PLACEHOLDER if is_sensitive_url(match.group(0)) else match.group(0)


def scrub_links(value) -> str:
    """``value`` with every personal sign-in link and token-shaped run replaced."""
    scrubbed = _URL_RE.sub(_replace, str(value or ""))
    return _LONG_TOKEN_RE.sub(REDACTED_PLACEHOLDER, scrubbed)


def scrub_subject(value, limit: int = 255) -> str:
    """A subject as stored: single-line, cleaned, scrubbed, at most ``limit`` characters."""
    return text.clean(scrub_links(text.clean(value, 4 * text.HEADER_LIMIT)), limit)
