"""
Server-side HTML sanitization for CMS content.

Defense-in-depth: the frontend also sanitizes via DOMPurify (SafeHtml component).
"""

import bleach

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

ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height", "loading"],
    "iframe": ["src", "width", "height", "frameborder", "allowfullscreen", "allow"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
    "*": ["class", "id", "style"],
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
