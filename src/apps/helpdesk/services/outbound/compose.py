"""What a helpdesk email says: the subject with the ticket token, the text with placeholders filled, and the HTML.

Every email about a ticket carries ``[I2G-#1234]`` in its subject: Microsoft Graph cannot send ``In-Reply-To`` or
``References`` (only ``x-`` headers), so the token is what threads the requester's answer back to the ticket (the
ingest accepts it only from a participant). Placeholders are plain text replacements; nothing in a template or a
reply is interpreted as a Django template. The values an outsider chose (their display name, the subject) lose
anything link-like before they are filled in.
"""

import re

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.mail.services.inbox.sending.reply import render_reply_html

from ...models import Ticket
from ..tickets import numbering

QUOTE_MAX_CHARS = 4000
_REPLY_PREFIX_RE = re.compile(r"^\s*((re|fw|fwd|aw|sv|antw)\s*:\s*)+", re.IGNORECASE)
# Top-level domains a mail client turns a bare host name ("payroll-update.example.com") into a link for.
_TLDS = (
    "com|net|org|edu|gov|mil|int|info|biz|name|pro|mobi|asia|io|co|me|ai|app|dev|cloud|tech|online|site|store|shop|"
    "page|link|live|email|click|work|club|top|xyz|zip|mov|tk|ml|ga|cf|gq|ws|cc|tv|ly|gl|su|us|uk|ca|de|fr|eu|nl|be|"
    "at|ch|it|es|pl|se|no|ru|cn|jp|kr|in|au|br"
)
# URLs, www. hosts, host names with a path ("evil.example/login"), bare host names on those top-level domains and IPv4
# addresses: anything a mail client may turn into a link.
_LINK_RE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|www\.)\S+"
    r"|\b[\w-]+(?:\.[\w-]+)+/\S*"
    rf"|\b(?:[a-z0-9-]+\.)+(?:{_TLDS})\b(?::\d+)?"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b(?::\d+)?",
    re.IGNORECASE,
)
# Marks an automatic message (RFC 3834) and asks Exchange not to answer it, so responders never answer each other.
AUTOMATIC_HEADERS = {"Auto-Submitted": "auto-replied", "X-Auto-Response-Suppress": "All"}
# The same for the site's own notices to staff (generated, not a reply to anything).
NOTICE_HEADERS = {"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"}


def person(member) -> str:
    if member is None:
        return ""
    return member.get_full_name() or str(member)


def without_links(value: str) -> str:
    """A value the sender of inbound mail chose (their display name, the subject), with anything link-like removed:
    filled into an email from the site's address, it must not carry an outsider's link (a phishing relay)."""
    return " ".join(_LINK_RE.sub("[link removed]", str(value or "")).split())


PLACEHOLDERS = ("{ticket}", "{requester_name}", "{subject}", "{agent_name}")
_PLACEHOLDER_RE = re.compile(r"\{[^{}\s]{1,40}\}")


def unknown_placeholders(text: str) -> list[str]:
    """The ``{...}`` tokens of ``text`` that are no placeholder (they would be sent as typed)."""
    return sorted(set(_PLACEHOLDER_RE.findall(str(text or ""))) - set(PLACEHOLDERS))


def fill(text: str, ticket: Ticket, *, agent=None) -> str:
    values = {
        "{ticket}": ticket.display_number,
        "{requester_name}": without_links(ticket.requester_name) or "there",
        "{subject}": without_links(ticket.subject) or "(no subject)",
        "{agent_name}": person(agent) or "the Innovate to Grow team",
    }
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    return text


def reply_subject(ticket: Ticket) -> str:
    subject = numbering.TOKEN_RE.sub("", without_links(ticket.subject)).replace("[]", "").strip()
    subject = _REPLY_PREFIX_RE.sub("", subject).strip() or "Your message"
    token = f" [{ticket.display_number}]"
    return f"Re: {subject[: 255 - len(token) - 4]}{token}"


def notice_subject(ticket: Ticket, what: str) -> str:
    return f"[{ticket.display_number}] {what}: {without_links(ticket.subject) or '(no subject)'}"[:255]


def footer(ticket: Ticket) -> str:
    number = ticket.display_number
    return f"Ticket {number}. Reply to this email to add to it, and keep {number} in the subject."


def _quote(quoted) -> tuple[str, str, str]:
    """(text, who wrote it, when, in the site's time zone with its name) of the message a reply answers."""
    if quoted is None or not quoted.body_text or quoted.body_purged_at:
        return "", "", ""
    when = timezone.localtime(quoted.occurred_at).strftime("%b %d, %Y %H:%M %Z") if quoted.occurred_at else ""
    return quoted.body_text[:QUOTE_MAX_CHARS], quoted.from_name or quoted.from_address, when


def reply_text(body: str, ticket: Ticket, quoted=None) -> str:
    """The plain-text reply: the message, the ticket footer and, like the HTML, the quoted message it answers."""
    text = f"{body.strip()}\n\n--\n{footer(ticket)}"
    quoted_text, original_from, original_date = _quote(quoted)
    if quoted_text:
        lines = "\n".join(f"> {line}" for line in quoted_text.splitlines())
        text += f"\n\nOn {original_date}, {original_from} wrote:\n{lines}"
    return text


def reply_html(body: str, ticket: Ticket, quoted=None) -> str:
    """The branded HTML of a reply (the Mail app's reply wrapper), quoting the message it answers when given."""
    quoted_text, original_from, original_date = _quote(quoted)
    return render_reply_html(reply_text(body, ticket), original_from, original_date, quoted_text)


def ticket_admin_url(ticket: Ticket) -> str:
    path = reverse("admin:helpdesk_ticket_change", args=[ticket.pk])
    base = str(getattr(settings, "BACKEND_URL", "") or "").rstrip("/")
    return f"{base}{path}"
