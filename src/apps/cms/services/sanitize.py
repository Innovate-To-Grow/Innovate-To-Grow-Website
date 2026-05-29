"""
Server-side HTML sanitization for CMS content.

Defense-in-depth: the frontend also sanitizes via DOMPurify (SafeHtml component).
"""

from urllib.parse import urlparse

import bleach

from .embed_hosts import InvalidEmbedURL, is_host_allowed, parse_embed_url

SAFE_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def validate_safe_url(url: str) -> bool:
    """Return True if url has a safe scheme or is a relative/fragment URL."""
    if not isinstance(url, str):
        return False
    trimmed = url.strip()
    if not trimmed:
        return False
    if trimmed.startswith(("#", "/", "./", "../")):
        return True
    parsed = urlparse(trimmed)
    if not parsed.scheme:
        return True
    return parsed.scheme.lower() in SAFE_URL_SCHEMES


ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "a",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "code",
    "pre",
    "img",
    "figure",
    "figcaption",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "iframe",
    "div",
    "span",
    "sub",
    "sup",
    "hr",
]

_IFRAME_STATIC_ATTRS = {"width", "height", "frameborder", "allowfullscreen", "allow"}


def _iframe_attr_filter(tag: str, name: str, value: str) -> bool:
    """Allow iframe attributes only with an explicitly allowlisted host on src."""
    if name in _IFRAME_STATIC_ATTRS:
        return True
    if name != "src":
        return False
    try:
        _, host = parse_embed_url(value or "")
    except InvalidEmbedURL:
        return False
    return is_host_allowed(host)


# Wildcard intentionally excludes `style` — inline CSS would let approved
# content overlay UI chrome (preview banners) or stage CSS-based phishing on
# public pages.
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height", "loading"],
    "iframe": _iframe_attr_filter,
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
    "*": ["class", "id"],
}


def sanitize_html(html: str) -> str:
    """Sanitize an HTML string, stripping disallowed tags and attributes."""
    if not html:
        return html
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


class _SanitizedHTML(str):
    """HTML string trusted only after passing through the CMS sanitizer."""

    def __html__(self) -> str:
        return str(self)


def sanitize_html_for_render(html: str | None) -> _SanitizedHTML:
    """Return sanitized CMS HTML approved for Django template rendering."""
    return _SanitizedHTML(sanitize_html(html or ""))
