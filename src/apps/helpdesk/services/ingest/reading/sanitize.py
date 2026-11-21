"""Sanitizing inbound HTML before it is stored, and the document it is shown in.

Defense in depth: the stored HTML is already safe, and the ticket page still shows it only inside an iframe whose
sandbox omits ``allow-scripts`` and ``allow-same-origin``, under the admin CSP (which blocks remote images, so
tracking pixels never load). Sanitizing keeps text formatting, lists, tables and links:

- elements that run, load or submit something are removed with their content (``script``, ``style``, ``iframe``,
  ``object``, ``embed``, ``form``, ``svg``, ``math``, ``base``, ``meta``, ``link``, media and form controls);
- images are replaced by a text placeholder (remote ones would track, inline ``cid:`` ones are listed as
  attachments);
- bleach keeps only the allow-listed tags, attributes and ``http``/``https``/``mailto``/``tel`` links (no event
  handlers, ``javascript:`` URLs or ``srcset``), and its CSS sanitizer only harmless style properties;
- every link opens in a new tab with ``rel="noopener noreferrer"``;
- personal sign-in links are scrubbed (``core``'s inbound ``scrub``), also one that inline formatting (``<span>``)
  splits, wherever it is cut, and a link to one is no link any more: its text stays, followed by
  ``[sign-in link removed]``. So is a Mimecast-rewritten link to the site's own host, also one Safe Links wrapped
  again: Mimecast names only that host, and sends the click on to the link it replaced (maybe a sign-in link).
"""

import re
from urllib.parse import parse_qs, urlsplit

import bleach
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup, Comment

from apps.core.services.email.inbound import LINK_PLACEHOLDER, is_sensitive_url, scrub_links, scrub_personal_links
from apps.core.services.email.inbound.processing.scrub import readings, site_hosts

ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "center", "cite", "code", "col", "colgroup", "dd", "del",
        "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "ins", "kbd", "li", "ol",
        "p", "pre", "q", "s", "small", "span", "strike", "strong", "sub", "sup", "table", "tbody", "td", "tfoot",
        "th", "thead", "tr", "tt", "u", "ul",
    }
)  # fmt: skip
_CELL = ["colspan", "rowspan", "width", "height", "bgcolor", "align", "valign", "nowrap"]
ALLOWED_ATTRIBUTES = {
    "*": ["style", "title", "dir", "lang", "align"],
    "a": ["href", "title"],
    "td": _CELL,
    "th": _CELL,
    "table": ["width", "border", "cellpadding", "cellspacing", "bgcolor", "align"],
    "col": ["span", "width"],
    "colgroup": ["span", "width"],
    "font": ["color", "face", "size"],
    "ol": ["start", "type"],
    "ul": ["type"],
}
ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto", "tel"})
ALLOWED_CSS_PROPERTIES = frozenset(
    {
        "color", "background-color", "font", "font-family", "font-size", "font-style", "font-weight",
        "font-variant", "text-align", "text-decoration", "text-indent", "text-transform", "line-height",
        "letter-spacing", "word-spacing", "white-space", "vertical-align", "margin", "margin-top", "margin-right",
        "margin-bottom", "margin-left", "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
        "border", "border-top", "border-right", "border-bottom", "border-left", "border-color", "border-style",
        "border-width", "border-collapse", "border-spacing", "border-radius", "width", "height", "max-width",
        "min-width", "list-style-type",
    }
)  # fmt: skip
# Removed together with everything inside them.
DROPPED_WITH_CONTENT = (
    "script", "style", "iframe", "frame", "frameset", "object", "embed", "applet", "form", "svg", "math", "base",
    "meta", "link", "head", "title", "noscript", "template", "audio", "video", "canvas", "button", "input", "select",
    "textarea", "picture", "source", "track", "map", "area",
)  # fmt: skip
IMAGE_PLACEHOLDER = "[image]"
# Most of a received HTML body that is parsed at all (a longer one is cut first, then sanitized and capped).
INPUT_MAX_CHARS = 4 * 1024 * 1024
_CSS = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)
_LINK_ATTRS = '<a rel="noopener noreferrer" target="_blank"'
# Room kept for the closing tags when a long body is cut.
_CLOSING_ROOM = 2048
# The sandboxed document's own look; an inline style attribute (the admin CSP allows those, never <style>).
_BODY_STYLE = (
    "margin:0;padding:12px;font:14px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;color:#111827;"
    "background:#ffffff;word-wrap:break-word;overflow-wrap:anywhere"
)
_MIMECAST_RE = re.compile(
    r"(?i)https?://(?:protect[a-z0-9-]*\.mimecast\.com|url\.[a-z0-9-]+\.m\.mimecastprotect\.com)/s/"
)
# Formatting a mail program puts inside a link's text (Word marks a "misspelt" token with <span class=SpellE>): a
# link run such tags split is judged as one link, wherever they cut it (also where no piece is long enough alone).
_INLINE_TAG = r"</?(?:span|b|i|u|em|strong|font|small|sub|sup|s|del|ins)\b[^>]*>"
_INLINE_TAG_RE = re.compile(_INLINE_TAG, re.IGNORECASE)
_SPLIT_LINK_RE = re.compile(rf"(?i)(?:https?:(?://|\\/\\/)|www\.)[^\s\"'<>]*(?:(?:{_INLINE_TAG})+[^\s\"'<>]+)+")
# The placeholder after an unlinked anchor's own text until the scrub has run: no token was cut there, so the words
# glued after it stay.
_UNLINKED = "\ue000"


def _prepare(html: str) -> str:
    soup = BeautifulSoup(html[:INPUT_MAX_CHARS].replace(_UNLINKED, ""), "html.parser")
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()
    for element in soup.find_all(DROPPED_WITH_CONTENT):
        element.decompose()
    for image in soup.find_all("img"):
        alt = str(image.get("alt") or "").strip()[:100]
        image.replace_with(f"[image: {alt}]" if alt else IMAGE_PLACEHOLDER)
    for anchor in soup.find_all("a", href=True):
        if _removed(str(anchor.get("href") or "")):
            _unlink(anchor)
    body = soup.body
    return "".join(str(child) for child in body.contents) if body is not None else str(soup)


def _removed(href: str) -> bool:
    """Whether scrubbing removes the link: a personal sign-in link (also a relative one), or one holding such a link,
    read as the browser reads it: it drops tabs and line breaks anywhere, and spaces and controls around it, and in an
    http(s) address (a relative one is resolved against the https page) it reads a backslash as a slash."""
    href = href.translate(_URL_BREAKS).strip("".join(map(chr, range(0x21))))
    # As written too: a mailto: link keeps its "\", and a "/" in its place could cut a token too short to be seen.
    return any(
        is_sensitive_url(read) or LINK_PLACEHOLDER in scrub_links(read) or _mimecast_to_the_site(read)
        for read in (href, href.replace("\\", "/"))
    )


_URL_BREAKS = str.maketrans("", "", "\t\n\r")


def _mimecast_to_the_site(href: str) -> bool:
    """Whether ``href`` is, or holds (wrapped again: Safe Links, Proofpoint), a Mimecast link to a site's own host."""
    for reading in readings(href):  # decoded as the scrubber decodes a wrapper
        for found in _MIMECAST_RE.finditer(reading):
            domains = parse_qs(urlsplit(reading[found.start() :]).query).get("domain", [])
            if any(domain.strip().lower().rstrip(".") in site_hosts() for domain in domains):
                return True
    return False


def _unlink(anchor) -> None:
    # Left as the href, the placeholder would be a link relative to the ticket page (it opens the admin): the anchor
    # goes, its content stays, followed by the placeholder unless its own text already shows one.
    text = anchor.get_text()
    if LINK_PLACEHOLDER not in scrub_links(text):
        anchor.append(f" {_UNLINKED}" if text.strip() else _UNLINKED)
    anchor.unwrap()


def _clean(html: str) -> str:
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_CSS,
        strip=True,
        strip_comments=True,
    )
    # bleach writes every kept anchor as "<a" + allow-listed attributes, which never include rel or target.
    return cleaned.replace("<a ", f"{_LINK_ATTRS} ").replace("<a>", f"{_LINK_ATTRS}>")


def sanitize_html(html: str, *, max_chars: int) -> tuple[str, bool]:
    """The sanitized, scrubbed HTML of a message body (at most ``max_chars``), and whether it was cut."""
    if not html or not html.strip():
        return "", False
    cut = len(html) > INPUT_MAX_CHARS
    cleaned = _scrubbed(_clean(_prepare(html)))
    if len(cleaned) > max_chars:
        # Cut with room to spare, then sanitize again: bleach re-parses the cut markup, drops a tag cut in half (so no
        # link is cut into a different one) and closes whatever it left open; the closing tags fit in the room left.
        room = max_chars - min(_CLOSING_ROOM, max_chars // 10)
        cleaned, cut = _trim(_scrubbed(_clean(cleaned[:room])), max_chars), True
    return cleaned.strip(), cut


def _scrubbed(html: str) -> str:
    """Serialized ``html`` scrubbed, a link that inline tags split judged as one."""
    return scrub_links(_SPLIT_LINK_RE.sub(_joined, html)).replace(_UNLINKED, LINK_PLACEHOLDER)


def _joined(found) -> str:
    """A link run that inline tags split, written whole when it holds a personal link (so the scrub sees all of it),
    its tags right after the placeholder: none is lost, so the markup stays well formed. Any other run stays as is."""
    split = found.group(0)
    kept = scrub_personal_links(_INLINE_TAG_RE.sub("", split))
    if LINK_PLACEHOLDER not in kept:
        return split
    head, _, tail = kept.partition(LINK_PLACEHOLDER)
    return head + LINK_PLACEHOLDER + "".join(_INLINE_TAG_RE.findall(split)) + tail


def _trim(html: str, max_chars: int) -> str:
    """At most ``max_chars`` of sanitized markup, never ending inside a tag."""
    html = html[:max_chars]
    opening = html.rfind("<")
    return html[:opening] if opening > html.rfind(">") else html


def frame_document(html: str) -> str:
    """The whole document a sanitized body is shown as (the ticket page escapes it into the iframe's ``srcdoc``)."""
    return f'<!doctype html><html><head><meta charset="utf-8"></head><body style="{_BODY_STYLE}">{html}</body></html>'
