"""Render an email campaign preview with sample personalization."""

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


def _get_logo_url():
    """Return the absolute static URL for the I2G logo."""
    from django.conf import settings

    return f"{settings.STATIC_URL}images/i2glogo.png"


def _text_to_html(text):
    """Convert plain text to HTML: escape special chars, convert newlines to <br>, and auto-link URLs."""
    import re

    escaped = escape(text)
    # Auto-link URLs
    escaped = re.sub(r"(https?://[^\s<>&]+)", r'<a href="\1" style="color:#0f2d52;">\1</a>', escaped)
    return escaped.replace("\n", "<br>\n")


def render_email_html(body_text):
    """Wrap *body_text* in the campaign email layout with logo.

    If the body starts with ``HTML_MARKER`` it is treated as raw HTML
    (marker stripped, no escaping/conversion).  Otherwise plain-text
    conversion is applied.
    """
    if body_text.startswith(HTML_MARKER):
        body_html = body_text[len(HTML_MARKER) :]
    else:
        body_html = _text_to_html(body_text)
    return render_to_string("mail/email/campaign_wrapper.html", {"body": body_html, "logo_url": _get_logo_url()})


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
    wrapped_html = render_email_html(body_html)
    return {"subject": subject, "html": wrapped_html}
