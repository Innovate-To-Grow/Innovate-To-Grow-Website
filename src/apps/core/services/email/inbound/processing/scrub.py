"""Removing personal sign-in links from inbound mail before anything of it is stored.

People reply quoting a blast, and the quote carries their personal links: ``/login-link#token=…`` (and the legacy
``/magic-login``), ``/impersonate-login#token=…``, one-click ``unsubscribe/<token>/`` and ``resubscribe/<token>/``,
the retired ``/unsubscribe-login``, the SMS short link ``/l/<token>`` on the site's own hosts (``FRONTEND_URL``,
``BACKEND_URL``), or any link with a ``token=`` (or ``…_token=``) parameter. A link starts at every ``http://``,
``https://`` (also JSON-escaped, ``https:\\/\\/``) and ``www.``, glued to a word or not, and a run of text without
spaces is read link by link (a ``www.`` inside a host starts none), so a CSV row or a sentence keeps its other links
and its words: a personal link is replaced by ``LINK_PLACEHOLDER`` up to where its token ends, and what follows the
token stays. A link that is personal only once unwrapped (percent-encoded in a "safe links" wrapper, or rewritten by
Proofpoint URL Defense) is replaced whole.

``scrub_links`` (what is stored of inbound mail) also replaces any remaining token-shaped run (60+ base64-ish
characters, as ``telemetry.text`` scrubs error texts) by ``REDACTED_PLACEHOLDER``. Inside any other link a token is one
path segment or parameter value (a run without "/" or "."), so a long but ordinary address (a shared document, a deep
page) is kept whole and still works. ``scrub_personal_links`` (what staff write, a requester's text file) replaces the
personal links only. Both read the text once, without recursion, and work on plain text and on serialized HTML alike
(attribute values are quoted, and ``&amp;`` is matched like ``&``).
"""

import base64
import re
import string
from functools import lru_cache, partial
from urllib.parse import unquote, urlsplit

from django.conf import settings

from ...telemetry import text

LINK_PLACEHOLDER = "[sign-in link removed]"
REDACTED_PLACEHOLDER = "[redacted]"

# A run starts at any "http(s)://" (JSON may write "https:\/\/") or "www.", glued to a word or not (Chinese text often
# has no space before a link, a calendar's "\n" escape none after it); a run that is no personal link stays as it was.
_URL_RE = re.compile(r"(?i)(?:https?:(?://|\\/\\/)|www\.)[^\s\"'<>]+")
# The next link inside a run: not the one a Proofpoint v3 wrapper holds ("/v3/__https://…"), and not a "www." right
# after "//" or a host's own characters (it is part of that host).
_LINK_START_RE = re.compile(r"(?i)(?<!/v3/__)(?<!\\/v3\\/__)https?:(?://|\\/\\/)|(?<!//)(?<!\\/)(?<![a-z0-9._-])www\.")
_SENSITIVE_PATH_RE = re.compile(
    r"(?i)/(?:login-link|magic-login|impersonate-login|unsubscribe-login)(?:[/?#]|$)|/(?:un|re)subscribe/[^/?#\s]{8,}"
)
_TOKEN_PARAM_RE = re.compile(r"(?i)[?#&;][a-z_]{0,32}token=")
# Where a personal link's token ends: past the characters a token holds (signed ".<base64>:<time>:<signature>",
# URL-safe base64, another site's token value, a ":" only with more of them after it), but before a final "." (a
# sentence's). A lookahead, so markers that overlap (one inside another's value) are all found and the furthest wins.
_TOKEN_END_RE = re.compile(
    r"(?i)(?=(/(?:login-link|magic-login|impersonate-login|unsubscribe-login)/?"
    r"|/(?:un|re)subscribe/[a-z0-9_.:-]+(?<!\.)/?"
    r"|[?#&;][a-z_]{0,32}token=[a-z0-9_.~%+/=-]*(?::[a-z0-9_.~%+/=-]+)*(?<!\.)))"
)
# Proofpoint URL Defense: v2 holds the link in "u=", "-XX" for a character and "_" for "/"; v3 between "__" marks, a
# "*" for each character it replaced ("**" and a letter for a run of them), those characters base64 after "__;".
_PROOFPOINT_RE = re.compile(
    r"(?i)https?://urldefense\.proofpoint\.com/v2/url\?u=([^&\s\"'<>]*)"
    r"|https?://urldefense\.com/v3/__([^\s\"'<>]*?)(?:__;([a-z0-9_-]*)|$)"
)
_V3_MARK_RE = re.compile(r"\*(?:\*(.))?")
_V3_RUNS = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"  # a run of 2, 3, … characters
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_.-]{60,}")
# Within a link: one segment or parameter value, so the run never spans a host, a path or a "name=" ("/", ".", "=").
_LINK_TOKEN_RE = re.compile(r"[A-Za-z0-9+_-]{60,}")
_REDACTED_IN_LINK = partial(_LINK_TOKEN_RE.sub, REDACTED_PLACEHOLDER)
_REDACTED_IN_TEXT = partial(_LONG_TOKEN_RE.sub, REDACTED_PLACEHOLDER)
# A link can be wrapped (percent-encoded) more than once; a few rounds of decoding find any such inner link.
_DECODE_ROUNDS = 3


def site_hosts() -> frozenset[str]:
    """The site's own host names, lower-case: ``FRONTEND_URL``'s and ``BACKEND_URL``'s (a missing setting: none)."""
    return frozenset(filter(None, (_host(getattr(settings, name, "")) for name in ("FRONTEND_URL", "BACKEND_URL"))))


@lru_cache(maxsize=16)
def _host(url) -> str:
    try:
        return urlsplit(str(url or "").strip()).hostname or ""
    except ValueError:  # a malformed address names no host
        return ""


@lru_cache(maxsize=8)
def _site_link_re(hosts: frozenset[str]):
    """The site's SMS short link on one of ``hosts``: ``/l/<token>``, the token the path's only segment."""
    if not hosts:
        return None
    names = "|".join(sorted(map(re.escape, hosts)))
    return re.compile(rf"(?i)(?<![a-z0-9.-])(?:{names})(?::\d+)?/l/[a-z0-9_-]{{16,64}}(?![a-z0-9_-])")


def _proofpoint(found) -> str:
    """The link a Proofpoint URL Defense wrapper holds."""
    v2, v3, characters = found.groups()
    if v2 is not None:
        return re.sub(r"-([0-9A-Fa-f]{2})", lambda hit: chr(int(hit.group(1), 16)), v2.replace("_", "/"))
    try:
        replaced = iter(base64.urlsafe_b64decode(f"{characters or ''}==").decode("utf-8", "replace"))
    except ValueError:
        replaced = iter("")

    def mark(hit) -> str:
        # A character that is lost reads as "#", the one a sign-in link's token follows.
        count = _V3_RUNS.find(hit.group(1)) + 2 if hit.group(1) else 1
        return "".join(next(replaced, "#") for _ in range(count))

    return _V3_MARK_RE.sub(mark, v3)


def _unwrapped(value: str) -> str:
    """``value`` with JSON's "\\/" read as "/", and each Proofpoint wrapper replaced by the link it holds."""
    return _PROOFPOINT_RE.sub(_proofpoint, value.replace("\\/", "/"))


def is_sensitive_url(url: str) -> bool:
    """Whether ``url`` is a personal sign-in or subscription link, or holds one: percent-encoded (a "safe links"
    wrapper), JSON-escaped, or wrapped by Proofpoint URL Defense."""
    candidate, site = _unwrapped(str(url or "")), _site_link_re(site_hosts())
    for _round in range(_DECODE_ROUNDS + 1):
        if _SENSITIVE_PATH_RE.search(candidate) or _TOKEN_PARAM_RE.search(candidate):
            return True
        if site is not None and site.search(candidate):
            return True
        decoded = _unwrapped(unquote(candidate))
        if decoded == candidate:
            return False
        candidate = decoded
    return False


def _token_end(piece: str) -> int:
    """Where the last token in sight in ``piece`` ends (0: none), a JSON-escaped "\\/" read as "/"."""
    plain, site = piece.replace("\\/", "/"), _site_link_re(site_hosts())
    ends = [found.end(1) for found in _TOKEN_END_RE.finditer(plain)]
    end = max(ends + ([found.end() for found in site.finditer(plain)] if site else []), default=0)
    shift = 0
    for escaped in re.finditer(r"\\/", piece):  # in ``piece`` each "\/" before the end is a character longer
        if escaped.start() - shift >= end:
            break
        shift += 1
    return end + shift


def _piece(piece: str, link, words) -> list[str]:
    """One link of a run and the text up to the next one."""
    if not is_sensitive_url(piece):
        return [link(piece)]
    end = _token_end(piece)
    # A wrapper holding a personal link (Proofpoint's, or one percent-encoded past the last token in sight) goes whole.
    if _PROOFPOINT_RE.match(piece.replace("\\/", "/")) or is_sensitive_url(piece[end:]):
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
