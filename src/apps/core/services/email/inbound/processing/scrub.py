"""Removing personal sign-in links from inbound mail before anything of it is stored.

People reply quoting a blast, and the quote carries their personal links: ``/login-link#token=…`` (and the legacy
``/magic-login``), ``/impersonate-login#token=…``, one-click ``unsubscribe/<token>/`` and ``resubscribe/<token>/``,
the retired ``/unsubscribe-login``, or any link with a ``token=`` (or ``…_token=``) parameter. A link starts at every
``http://``, ``https://`` and ``www.``, glued to a word or not, and a run of text without spaces is read link by link
(a ``www.`` inside a host starts none), so a CSV row or a sentence keeps its other links and its words: a personal
link is replaced by ``LINK_PLACEHOLDER`` up to where its token ends, and what follows the token stays. A link that is
personal only because one is percent-encoded inside it (a "safe links" wrapper) is replaced whole.

``scrub_links`` (what is stored of inbound mail) also replaces any remaining token-shaped run (60+ base64-ish
characters, as ``telemetry.text`` scrubs error texts) by ``REDACTED_PLACEHOLDER``. Inside any other link a token is one
path segment or parameter value (a run without "/" or "."), so a long but ordinary address (a shared document, a deep
page) is kept whole and still works. ``scrub_personal_links`` (what staff write, a requester's text file) replaces the
personal links only. Both read the text once, without recursion, and work on plain text and on serialized HTML alike
(attribute values are quoted, and ``&amp;`` is matched like ``&``).
"""

import re
from functools import partial
from urllib.parse import unquote

from ...telemetry import text

LINK_PLACEHOLDER = "[sign-in link removed]"
REDACTED_PLACEHOLDER = "[redacted]"

# A run starts at any "http(s)://" or "www.", glued to a word or not (Chinese text often has no space before a link,
# a calendar's "\n" escape none after it); a run that is no personal link stays as it was.
_URL_RE = re.compile(r"(?i)(?:https?://|www\.)[^\s\"'<>]+")
# The next link inside a run: a "www." right after "//" or a host's own characters is part of that host.
_LINK_START_RE = re.compile(r"(?i)https?://|(?<!//)(?<![a-z0-9._-])www\.")
_SENSITIVE_PATH_RE = re.compile(
    r"(?i)/(?:login-link|magic-login|impersonate-login|unsubscribe-login)(?:[/?#]|$)|/(?:un|re)subscribe/[^/?#\s]{8,}"
)
_TOKEN_PARAM_RE = re.compile(r"(?i)[?#&;][a-z_]{0,32}token=")
# Where a personal link's token ends: past the characters a token holds (signed ".<base64>:<time>:<signature>",
# URL-safe base64, another site's token value), but before a final "." (a sentence's). A lookahead, so markers that
# overlap (one inside another's value) are all found and the furthest end wins.
_TOKEN_END_RE = re.compile(
    r"(?i)(?=(/(?:login-link|magic-login|impersonate-login|unsubscribe-login)/?"
    r"|/(?:un|re)subscribe/[a-z0-9_.:-]+(?<!\.)/?"
    r"|[?#&;][a-z_]{0,32}token=[a-z0-9_.~%+/=-]*(?<!\.)))"
)
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_.-]{60,}")
# Within a link: one segment or parameter value, so the run never spans a host, a path or a "name=" ("/", ".", "=").
_LINK_TOKEN_RE = re.compile(r"[A-Za-z0-9+_-]{60,}")
_REDACTED_IN_LINK = partial(_LINK_TOKEN_RE.sub, REDACTED_PLACEHOLDER)
_REDACTED_IN_TEXT = partial(_LONG_TOKEN_RE.sub, REDACTED_PLACEHOLDER)
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


def _piece(piece: str, link, words) -> list[str]:
    """One link of a run and the text up to the next one."""
    if not is_sensitive_url(piece):
        return [link(piece)]
    end = max((found.end(1) for found in _TOKEN_END_RE.finditer(piece)), default=0)
    # A personal link percent-encoded in this one (no token in sight, or one past the last visible): all of it goes.
    if is_sensitive_url(piece[end:]):
        return [LINK_PLACEHOLDER]
    return [LINK_PLACEHOLDER, words(piece[end:])]


def _scrubbed(value, link, words) -> str:
    """``value`` with every personal link replaced; ``link`` writes the other links, ``words`` all other text."""
    value, parts, start = str(value or ""), [], 0
    for run in _URL_RE.finditer(value):
        parts.append(words(value[start : run.start()]))
        starts = [found.start() for found in _LINK_START_RE.finditer(value, run.start() + 1, run.end())]
        for begin, end in zip([run.start(), *starts], [*starts, run.end()], strict=True):
            parts += _piece(value[begin:end], link, words)
        start = run.end()
    parts.append(words(value[start:]))
    return "".join(parts)


def scrub_links(value) -> str:
    """``value`` with every personal sign-in link and token-shaped run replaced: any other link loses only a
    token-shaped segment, the text around links (also right after a personal one) every token-shaped run."""
    return _scrubbed(value, _REDACTED_IN_LINK, _REDACTED_IN_TEXT)


def scrub_personal_links(value) -> str:
    """``value`` with only its personal sign-in and subscription links replaced: every other link (long ones too) and
    the text around them, right after such a link included, is kept as written."""
    return _scrubbed(value, str, str)


def scrub_subject(value, limit: int = 255) -> str:
    """A subject as stored: single-line, cleaned, scrubbed, at most ``limit`` characters."""
    return text.clean(scrub_links(text.clean(value, 4 * text.HEADER_LIMIT)), limit)
