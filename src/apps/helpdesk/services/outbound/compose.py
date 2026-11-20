"""What a helpdesk email says: the subject with the ticket token, the text with placeholders filled, and the HTML.

Every email about a ticket carries ``[I2G-#1234]`` in its subject: Microsoft Graph cannot send ``In-Reply-To`` or
``References`` (only ``x-`` headers), so the token is what threads the requester's answer back to the ticket (the
ingest accepts it only from a participant). Placeholders are plain text replacements; nothing in a template or a
reply is interpreted as a Django template.
"""

import re

from django.conf import settings
from django.urls import reverse

from apps.mail.services.inbox.reply import render_reply_html

from ...models import Ticket
from ..tickets import numbering

QUOTE_MAX_CHARS = 4000
_REPLY_PREFIX_RE = re.compile(r"^\s*((re|fw|fwd|aw|sv|antw)\s*:\s*)+", re.IGNORECASE)


def person(member) -> str:
    if member is None:
        return ""
    return member.get_full_name() or str(member)


def fill(text: str, ticket: Ticket, *, agent=None) -> str:
    values = {
        "{ticket}": ticket.display_number,
        "{requester_name}": ticket.requester_name or "there",
        "{subject}": ticket.subject or "(no subject)",
        "{agent_name}": person(agent) or "the Innovate to Grow team",
    }
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    return text


def reply_subject(ticket: Ticket) -> str:
    subject = numbering.TOKEN_RE.sub("", ticket.subject or "").replace("[]", "").strip()
    subject = _REPLY_PREFIX_RE.sub("", subject).strip() or "Your message"
    token = f" [{ticket.display_number}]"
    return f"Re: {subject[: 255 - len(token) - 4]}{token}"


def notice_subject(ticket: Ticket, what: str) -> str:
    return f"[{ticket.display_number}] {what}: {ticket.subject or '(no subject)'}"[:255]


def footer(ticket: Ticket) -> str:
    number = ticket.display_number
    return f"Ticket {number}. Reply to this email to add to it, and keep {number} in the subject."


def reply_text(body: str, ticket: Ticket) -> str:
    return f"{body.strip()}\n\n--\n{footer(ticket)}"


def reply_html(body: str, ticket: Ticket, quoted=None) -> str:
    """The branded HTML of a reply (the Mail app's reply wrapper), quoting the message it answers when given."""
    quoted_text = original_from = original_date = ""
    if quoted is not None and quoted.body_text and not quoted.body_purged_at:
        quoted_text = quoted.body_text[:QUOTE_MAX_CHARS]
        original_from = quoted.from_name or quoted.from_address
        original_date = quoted.occurred_at.strftime("%b %d, %Y %H:%M") if quoted.occurred_at else ""
    return render_reply_html(reply_text(body, ticket), original_from, original_date, quoted_text)


def ticket_admin_url(ticket: Ticket) -> str:
    path = reverse("admin:helpdesk_ticket_change", args=[ticket.pk])
    base = str(getattr(settings, "BACKEND_URL", "") or "").rstrip("/")
    return f"{base}{path}"
