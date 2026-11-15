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
- personal sign-in links are scrubbed (``core``'s inbound ``scrub``).
"""

import bleach
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup, Comment

from apps.core.services.email.inbound import scrub_links

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


def _prepare(html: str) -> str:
    soup = BeautifulSoup(html[:INPUT_MAX_CHARS], "html.parser")
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()
    for element in soup.find_all(DROPPED_WITH_CONTENT):
        element.decompose()
    for image in soup.find_all("img"):
        alt = str(image.get("alt") or "").strip()[:100]
        image.replace_with(f"[image: {alt}]" if alt else IMAGE_PLACEHOLDER)
    body = soup.body
    return "".join(str(child) for child in body.contents) if body is not None else str(soup)


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
    cleaned = scrub_links(_clean(_prepare(html)))
    if len(cleaned) > max_chars:
        # Cut with room to spare, then sanitize again: bleach re-parses the cut markup and closes whatever it left
        # open, and the closing tags it adds fit in the room left.
        room = max_chars - min(_CLOSING_ROOM, max_chars // 10)
        cleaned, cut = _trim(scrub_links(_clean(cleaned[:room])), max_chars), True
    return cleaned.strip(), cut


def _trim(html: str, max_chars: int) -> str:
    """At most ``max_chars`` of sanitized markup, never ending inside a tag."""
    html = html[:max_chars]
    opening = html.rfind("<")
    return html[:opening] if opening > html.rfind(">") else html


def frame_document(html: str) -> str:
    """The whole document a sanitized body is shown as (the ticket page escapes it into the iframe's ``srcdoc``)."""
    return f'<!doctype html><html><head><meta charset="utf-8"></head><body style="{_BODY_STYLE}">{html}</body></html>'
