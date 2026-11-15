"""The ticket page's timeline: messages, internal notes and field changes in time order.

Message HTML is shown only through ``frame_document`` inside an iframe whose sandbox omits ``allow-scripts`` and
``allow-same-origin`` (the template escapes the document into ``srcdoc``); text bodies are shown as text. Automated
messages are collapsed. Attachment content is never loaded here, only whether it is stored.
"""

from dataclasses import dataclass, field
from datetime import datetime

from django.db.models import BooleanField, ExpressionWrapper, Prefetch, Q
from django.urls import reverse

from apps.core.services.email.inbound import LABELS

from ..models import HelpdeskSettings, Ticket, TicketAttachment, TicketEvent, TicketMessage
from ..services import events
from ..services.ingest import attachments as files
from ..services.ingest.sanitize import frame_document

# Events that repeat what a message entry already shows.
_IMPLIED_BY_MESSAGES = (TicketEvent.Kind.CUSTOMER_MESSAGE, TicketEvent.Kind.AUTOMATED_MESSAGE, TicketEvent.Kind.NOTE)


@dataclass
class Entry:
    kind: str  # customer, automated, note or event
    at: datetime
    message: TicketMessage | None = None
    text: str = ""
    actor: str = ""
    frame: str = ""
    label: str = ""
    attachments: list = field(default_factory=list)


def _attachment_rows(ticket: Ticket, message: TicketMessage, settings: HelpdeskSettings) -> list[dict]:
    rows = []
    for attachment in message.attachments.all():
        rows.append(
            {
                "filename": attachment.filename,
                "size": attachment.size,
                "type": attachment.detected_type or attachment.declared_type,
                "stored": attachment.has_content,
                "reason": attachment.not_stored_reason or ("Purged by retention." if attachment.purged_at else ""),
                "blocked": attachment.blocked,
                "warning": files.needs_warning(attachment, settings),
                "inline": attachment.is_inline,
                "url": reverse("admin:helpdesk_ticket_attachment", args=[ticket.pk, attachment.pk]),
            }
        )
    return rows


def _actor(member) -> str:
    return (member.get_full_name() or str(member)) if member is not None else ""


def build(ticket: Ticket, settings: HelpdeskSettings | None = None) -> list[Entry]:
    settings = settings or HelpdeskSettings.load()
    stored = ExpressionWrapper(Q(content__isnull=False), output_field=BooleanField())
    attachments = TicketAttachment.objects.defer("content").annotate(has_content=stored)
    messages = (
        TicketMessage.objects.filter(ticket=ticket)
        .select_related("author")
        .prefetch_related(Prefetch("attachments", queryset=attachments))
    )
    entries = [
        Entry(
            kind=message.kind,
            at=message.occurred_at,
            message=message,
            actor=_actor(message.author),
            frame=frame_document(message.body_html) if message.body_html else "",
            label=LABELS.get(message.classification, "") if message.kind == TicketMessage.Kind.AUTOMATED else "",
            attachments=_attachment_rows(ticket, message, settings),
        )
        for message in messages
    ]
    trail = TicketEvent.objects.filter(ticket=ticket).exclude(kind__in=_IMPLIED_BY_MESSAGES).select_related("actor")
    entries += [
        Entry(kind="event", at=event.created_at, text=events.describe(event), actor=_actor(event.actor))
        for event in trail
    ]
    entries.sort(key=lambda entry: entry.at)
    return entries
