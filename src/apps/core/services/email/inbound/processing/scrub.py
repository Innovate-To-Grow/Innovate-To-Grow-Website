"""Removing personal sign-in links from inbound mail before anything of it is stored.

People reply quoting a blast, and the quote carries their personal links: ``/login-link#token=…`` (and the legacy
``/magic-login`` and ``/ticket-login``), ``/impersonate-login#token=…``, the email sign-in link sent with every login
and registration code (``/email-auth-link#…&code=…``), one-click ``unsubscribe/<token>/`` and ``resubscribe/<token>/``,
the retired ``/unsubscribe-login``, the SMS short link ``/l/<token>`` on the site's own hosts (``FRONTEND_URL``,
``BACKEND_URL``), or any link with a ``token=`` (or ``…_token=``) parameter. A link starts at every ``http://``,
``https://`` (also JSON-escaped, ``https:\\/\\/``) and ``www.``, glued to a word or not, and a run of text without
spaces is read link by link (a ``www.`` inside a host starts none), so a CSV row or a sentence keeps its other links
and its words: a personal link is replaced by ``LINK_PLACEHOLDER`` up to where its token ends, and what follows the
token stays (the site's own sign-in token ends at the first character ``secrets.token_urlsafe`` never writes, a
percent-encoded one counted in; the email sign-in link at the end of its parameters; another site's ``token=`` value
may hold "." and ":", as a signed ``payload:time:signature`` does). A link that is personal only once unwrapped
(percent-encoded in a "safe links" wrapper, or rewritten by Proofpoint URL Defense) goes whole.

``scrub_links`` (what is stored of inbound mail) also replaces any remaining token-shaped run (60+ base64-ish
characters, as ``telemetry.text`` scrubs error texts) by ``REDACTED_PLACEHOLDER``. Inside any other link a token is one
path segment or parameter value (a run without "/" or "."), so a long but ordinary address (a shared document, a deep
page, a Microsoft Forms link, whose ``id=`` names the form) is kept whole and still works; so is a gateway's wrapper
(Safe Links, Proofpoint), judged by the link it holds (``gateways``), its own parameters as written.
``scrub_personal_links`` (what staff write, a requester's text file) replaces the personal links only. Both read the
text once, without recursion, and work on plain text and on serialized HTML alike (attribute values are quoted, and
``&amp;`` is matched like ``&``).
"""

import re
from collections.abc import Iterator
from functools import lru_cache, partial
from urllib.parse import unquote, urlsplit

from django.conf import settings

from ...telemetry import text
from . import gateways

LINK_PLACEHOLDER = "[sign-in link removed]"
REDACTED_PLACEHOLDER = "[redacted]"

# A run starts at any "http(s)://" (JSON may write "https:\/\/") or "www.", glued to a word or not (Chinese text often
# has no space before a link, a calendar's "\n" escape none after it); a run that is no personal link stays as it was.
_URL_RE = re.compile(r"(?i)(?:https?:(?://|\\/\\/)|www\.)[^\s\"'<>]+")
# The next link inside a run: not the one a Proofpoint v3 wrapper holds ("/v3/__https://…"), and not a "www." right
# after "//" or a host's own characters (it is part of that host).
_LINK_START_RE = re.compile(r"(?i)(?<!/v3/__)(?<!\\/v3\\/__)https?:(?://|\\/\\/)|(?<!//)(?<!\\/)(?<![a-z0-9._-])www\.")
_SENSITIVE_PATH_RE = re.compile(
    r"(?i)/(?:login-link|magic-login|ticket-login|impersonate-login|unsubscribe-login|email-auth-link)(?:[/?#]|$)"
    r"|/(?:un|re)subscribe/[^/?#\s]{8,}"
)
_TOKEN_PARAM_RE = re.compile(r"(?i)[?#&;][a-z_]{0,32}token=")
# Where a personal link's token ends: past the characters a token holds (signed ".<base64>:<time>:<signature>",
# URL-safe base64, another site's token value, a ":" only with more of them after it), but before a final "." (a
# sentence's). A lookahead, so markers that overlap (one inside another's value) are all found and the furthest wins.
# The email sign-in link holds its code among parameters as ``urlencode`` writes them ("&amp;" in HTML; "&" only before
# a name, so "&gt;" is none): all of them go, the code its digits (".Thanks" glued on stays), not a sentence's ".".
_PAIR = r"(?:code=\d*|[a-z_]+=[a-z0-9_.~%+-]*)"
_PATH_ENDS = (
    r"/(?:login-link|magic-login|ticket-login|impersonate-login|unsubscribe-login)/?"
    r"|/email-auth-link/?(?:[?#]" + _PAIR + r"(?:&(?:amp;)*" + _PAIR + r")*(?<!\.))?"
    r"|/(?:un|re)subscribe/[a-z0-9_.:-]+(?<!\.)/?"
)
_TOKEN_END_RE = re.compile(
    rf"(?i)(?=({_PATH_ENDS}|[?#&;][a-z_]{{0,32}}token=[a-z0-9_.~%+/=-]*(?::[a-z0-9_.~%+/=-]+)*(?<!\.)))"
)
# The site's own sign-in links hold a ``secrets.token_urlsafe`` token ([A-Za-z0-9_-]), so a word glued after one
# (":it failed", ".Thanks", "/or") is no part of it; a percent-encoded character is (the site's page decodes the
# token, "%51" reads "Q"). The retired /unsubscribe-login's token was signed, as above.
_OWN_SIGN_IN_RE = re.compile(r"(?i)[^?#]*/(?:login-link|magic-login|ticket-login|impersonate-login)/?(?:[?#]|$)")
_OWN_TOKEN_END_RE = re.compile(rf"(?i)(?=({_PATH_ENDS}|[?#&;][a-z_]{{0,32}}token=(?:[a-z0-9_-]|%[0-9a-f]{{2}})*))")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_.-]{60,}")
# Within a link: one segment or parameter value, so the run never spans a host, a path or a "name=" ("/", ".", "=").
_LINK_TOKEN_RE = re.compile(r"[A-Za-z0-9+_-]{60,}")
# A Microsoft Forms link's "id=" names the form (shared with whoever may answer it), not a person.
_FORMS_RE = re.compile(r"(?i)https?://forms\.(?:office\.com|microsoft\.com|cloud\.microsoft)/")
_FORM_ID_KEPT_RE = re.compile(r"(?<![A-Za-z0-9+_-])(?<![?&;]id=)[A-Za-z0-9+_-]{60,}")
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


def readings(url) -> Iterator[str]:
    """``url`` as each round of decoding reads it (JSON's "\\/" and a Proofpoint wrapper read from the first, then
    percent-encoding), so that a link a gateway wrapped, once or more than once, is seen too."""
    candidate = gateways.unwrapped(str(url or ""))
    for _round in range(_DECODE_ROUNDS + 1):
        yield candidate
        decoded = gateways.unwrapped(unquote(candidate))
        if decoded == candidate:
            return
        candidate = decoded


def is_sensitive_url(url: str) -> bool:
    """Whether ``url`` is a personal sign-in or subscription link, or holds one: percent-encoded (a "safe links"
    wrapper), JSON-escaped, or wrapped by Proofpoint URL Defense."""
    site = _site_link_re(site_hosts())
    return any(
        _SENSITIVE_PATH_RE.search(reading) or _TOKEN_PARAM_RE.search(reading) or (site and site.search(reading))
        for reading in readings(url)
    )


def _token_end(piece: str) -> int:
    """Where the last token in sight in ``piece`` ends (0: none), a JSON-escaped "\\/" read as "/"."""
    plain, site = piece.replace("\\/", "/"), _site_link_re(site_hosts())
    markers = _OWN_TOKEN_END_RE if _OWN_SIGN_IN_RE.match(plain) else _TOKEN_END_RE
    ends = [found.end(1) for found in markers.finditer(plain)]
    end = max(ends + ([found.end() for found in site.finditer(plain)] if site else []), default=0)
    shift = 0
    for escaped in re.finditer(r"\\/", piece):  # in ``piece`` each "\/" before the end is a character longer
        if escaped.start() - shift >= end:
            break
        shift += 1
    return end + shift


def _segments_redacted(link: str) -> str:
    """``link`` with each token-shaped segment or parameter value replaced (a Forms link keeps its form's id)."""
    return (_FORM_ID_KEPT_RE if _FORMS_RE.match(link) else _LINK_TOKEN_RE).sub(REDACTED_PLACEHOLDER, link)


def _backstopped(link: str) -> str:
    """``link`` (no personal one) without its token-shaped segments. A gateway's wrapper (also one inside another) is
    judged by the link it holds, decoded: its own parameters stay as written, so an ordinary link still works."""
    wrapper = gateways.held(link)
    if wrapper is None:
        return _segments_redacted(link)
    start, end, own, inner = wrapper
    for _round in range(_DECODE_ROUNDS):
        if (deeper := gateways.held(inner)) is None:
            break
        inner = deeper[3]
    written = link[start:end]
    # A token in the link it holds goes as written there, or with all of that link if only decoding shows it ("%2B").
    if _segments_redacted(inner) != inner:
        redacted = _segments_redacted(written)
        written = redacted if redacted != written else REDACTED_PLACEHOLDER
    return link[:start] + written + link[end:own] + _segments_redacted(link[own:])


def _piece(piece: str, link, words) -> list[str]:
    """One link of a run and the text up to the next one."""
    if not is_sensitive_url(piece):
        return [link(piece)]
    end = _token_end(piece)
    # A wrapper holding a personal link (Proofpoint's, or one percent-encoded past the last token in sight) goes whole.
    if gateways.is_proofpoint(piece) or is_sensitive_url(piece[end:]):
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
    return _scrubbed(value, _backstopped, _REDACTED_IN_TEXT)


def scrub_personal_links(value) -> str:
    """``value`` with only its personal sign-in and subscription links replaced: every other link (long ones too) and
    the text around them, right after such a link included, is kept as written."""
    return _scrubbed(value, str, str)


def scrub_subject(value, limit: int = 255) -> str:
    """A subject as stored: single-line, cleaned, scrubbed, at most ``limit`` characters."""
    return text.clean(scrub_links(text.clean(value, 4 * text.HEADER_LIMIT)), limit)
