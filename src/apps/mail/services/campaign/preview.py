"""Render an email campaign preview with sample personalization."""

import re

from django.template.loader import render_to_string
from django.utils.html import escape

from .personalize import personalize

HTML_MARKER = "<!-- raw-html -->\n"

SAMPLE_CONTEXT = {
    "first_name": "Hongzhe",
    "last_name": "Xie",
    "full_name": "Hongzhe Xie",
    "login_link": "#",
}

_URL_RE = re.compile(r"https?://[^\s<>&]+")
# Sentence punctuation that trails a URL in prose ("see https://x.example.") but is not part of it.
_TRAILING_PUNCTUATION = ".,;:!?'\"\u2019\u201d"
_CLOSING_TO_OPENING = {")": "(", "]": "[", "}": "{"}


def _get_logo_url():
    """Return the absolute static URL for the I2G logo."""
    from django.conf import settings

    return f"{settings.STATIC_URL}images/i2glogo.png"


def _split_trailing_punctuation(url):
    """Split *url* into ``(link, trailing)`` where *trailing* is prose punctuation, not part of the URL.

    A closing bracket is only treated as punctuation when it is unbalanced within the URL, so
    ``https://x.example/a_(b)`` stays whole while ``(https://x.example/a)`` loses its ``)``.
    """
    end = len(url)
    while end > 0:
        char = url[end - 1]
        if char in _TRAILING_PUNCTUATION:
            end -= 1
        elif char in _CLOSING_TO_OPENING and url[:end].count(char) > url[:end].count(_CLOSING_TO_OPENING[char]):
            end -= 1
        else:
            break
    return url[:end], url[end:]


def _link_url(match):
    link, trailing = _split_trailing_punctuation(match.group(0))
    return f'<a href="{link}" style="color:#0f2d52;">{link}</a>{trailing}'


def _text_to_html(text):
    """Convert plain text to HTML: escape special chars, convert newlines to <br>, and auto-link URLs.

    Trailing sentence punctuation is emitted after the ``</a>`` so it never becomes part of the href
    (which would corrupt token URLs such as the campaign ``{{login_link}}``).
    """
    escaped = _URL_RE.sub(_link_url, escape(text))
    return escaped.replace("\n", "<br>\n")


def build_email_render_context(body_text, unsubscribe_url=""):
    """Build the trusted template context used by campaign email rendering.

    If the body starts with ``HTML_MARKER`` it is treated as raw HTML
    (marker stripped, no escaping/conversion).  Otherwise plain-text
    conversion is applied.
    """
    if body_text.startswith(HTML_MARKER):
        body_html = body_text[len(HTML_MARKER) :]
    else:
        body_html = _text_to_html(body_text)
    return {"body": body_html, "logo_url": _get_logo_url(), "unsubscribe_url": unsubscribe_url}


def render_email_html(body_text, unsubscribe_url=""):
    """Wrap *body_text* in the campaign email layout with logo."""
    return render_to_string(
        "mail/email/campaign_wrapper.html",
        build_email_render_context(body_text, unsubscribe_url=unsubscribe_url),
    )


def render_preview(campaign, context=None):
    """
    Return a fully rendered email preview for *campaign*.

    Uses *context* for personalization placeholders, falling back to
    ``SAMPLE_CONTEXT`` when not provided.

    Returns ``{"subject": str, "html": str}``.
    """
    ctx = context or SAMPLE_CONTEXT
    subject = personalize(campaign.subject, ctx)
    body_html = personalize(campaign.body, ctx)
    # Show a placeholder unsubscribe link when the campaign has it enabled
    unsubscribe_url = "#unsubscribe-preview" if campaign.include_unsubscribe_header else ""
    wrapped_html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
    return {"subject": subject, "html": wrapped_html}
