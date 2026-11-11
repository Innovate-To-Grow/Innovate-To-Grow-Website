"""Storing one classified inbound message: on the ticket it belongs to, or on a new one.

The rules (Hongzhe's decision of 2026-11-11 on top of item2-helpdesk-bounces-plan §2.4):

- Every message is stored once (``fingerprint``); a second copy of it only marks the inbound row as a duplicate.
- Automated mail joins the ticket it threads to as a collapsed entry and changes nothing on it (no reopening, no
  unread mark, no new activity time). Otherwise it opens a ticket that is closed at once, ``automated`` (hidden from
  the default queue), with low priority; spam is closed as spam. Nothing is ever sent for it.
- A person's message (or an uncertain one) joins the ticket it threads to, unless that ticket is automated or spam:
  then it opens a new ticket linked to it. A ticket closed less than ``reopen_window_days`` before the message arrived
  reopens; an older one gets a linked follow-up ticket. A sender with more than ``flood_threshold`` new tickets within
  ``flood_window_minutes`` has the next one grouped into their latest ticket, which is flagged.
- The site's own messages keep no body or attachment (they may hold sign-in codes).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.models import InboundMessage
from apps.core.services.email.inbound import scrub_links, scrub_subject
from apps.mail.models import EmailCampaign

from ...models import HelpdeskSettings, Ticket, TicketAttachment, TicketEvent, TicketMessage
from .. import events, numbering
from . import attachments, matching
from .classify import Classified
from .parse import ParsedMessage
from .sanitize import sanitize_html

Status = Ticket.Status
OWN_MAIL_NOTE = "Sent from the site's own address: its content is not stored (it may hold sign-in codes)."
MAX_PARTICIPANTS = 50
MAX_REFERENCES = 20


@dataclass(frozen=True)
class Stored:
    ticket: Ticket
    message: TicketMessage | None
    created: bool = False
    duplicate: bool = False
    rule: str = ""


def store(
    row: InboundMessage, parsed: ParsedMessage, classified: Classified, settings: HelpdeskSettings, *, own: frozenset
) -> Stored:
    fingerprint = parsed.fingerprint()
    with transaction.atomic():
        duplicate = (
            TicketMessage.objects.select_related("ticket")
            .filter(fingerprint=fingerprint, kind__in=TicketMessage.INBOUND_KINDS)
            .first()
        )
        if duplicate is not None:
            return Stored(duplicate.ticket, None, duplicate=True, rule="duplicate")
        match = matching.find(parsed, conversation_id=row.conversation_id, prefer_human=not classified.automated)
        ticket, created, rule = _target(match, parsed, classified, settings, row.received_at, own)
        message = _add_message(ticket, row, parsed, classified, settings, fingerprint)
        if not created:
            _joined(ticket, message, classified, rule, own)
        for number in match.mentions:
            events.record(ticket, TicketEvent.Kind.MENTION, number=number)
    return Stored(ticket, message, created=created, rule=rule)


def _target(match, parsed, classified, settings, received: datetime, own) -> tuple[Ticket, bool, str]:
    new = {"parsed": parsed, "classified": classified, "settings": settings, "received": received, "own": own}
    if match.ticket is not None:
        ticket = Ticket.objects.select_for_update().get(pk=match.ticket.pk)
        if classified.automated:
            return ticket, False, match.rule
        if ticket.automated or ticket.status in (Status.SPAM, Status.MERGED):
            return _new(**new, campaign_id=match.campaign_id, related=ticket, rule="related"), True, "related"
        if ticket.status in (Status.RESOLVED, Status.CLOSED):
            window = timedelta(days=int(settings.reopen_window_days))
            if ticket.closed_at is None or received - ticket.closed_at <= window:
                return ticket, False, "reopened"
            return _new(**new, campaign_id=match.campaign_id, related=ticket, rule="follow_up"), True, "follow_up"
        return ticket, False, match.rule
    if not classified.automated:
        grouped = _flood_target(parsed.from_address, settings, received)
        if grouped is not None:
            return grouped, False, "flood"
    return _new(**new, campaign_id=match.campaign_id, rule="new"), True, "new"


def _flood_target(address: str, settings: HelpdeskSettings, received: datetime) -> Ticket | None:
    if not address:
        return None
    since = received - timedelta(minutes=int(settings.flood_window_minutes))
    recent = Ticket.objects.filter(
        requester_email=address, automated=False, first_message_at__gte=since, first_message_at__lte=received
    ).exclude(status__in=(Status.MERGED, Status.SPAM))
    if recent.count() < int(settings.flood_threshold):
        return None
    return recent.select_for_update().order_by("-first_message_at").first()


def _participants(addresses, own) -> list[str]:
    return [address for address in dict.fromkeys(addresses) if address and address not in own][:MAX_PARTICIPANTS]


def _member_for(address: str):
    if not address:
        return None
    contact = (
        ContactEmail.objects.filter(email_address__iexact=address, member__isnull=False)
        .select_related("member")
        .first()
    )
    return contact.member if contact is not None else None


def _new(*, parsed, classified, settings, received, own, campaign_id, rule, related=None) -> Ticket:
    automated = classified.automated
    verdict = classified.verdict
    closed_status = Status.SPAM if verdict.classification == "spam" else Status.CLOSED
    ticket = numbering.create_ticket(
        subject=scrub_subject(parsed.subject) or "(no subject)",
        status=closed_status if automated else Status.NEW,
        priority=Ticket.Priority.LOW if automated else Ticket.Priority.NORMAL,
        requester_email=parsed.from_address[:254],
        requester_name=scrub_subject(parsed.from_name),
        requester_member=_member_for(parsed.from_address),
        participants=_participants([parsed.from_address, parsed.reply_to, *parsed.to, *parsed.cc], own),
        campaign=EmailCampaign.objects.filter(pk=campaign_id).first() if campaign_id else None,
        related_ticket=related,
        classification=verdict.classification,
        automated=automated,
        flags=list(classified.flags),
        unread=not automated,
        backfilled=timezone.now() - received > timedelta(hours=int(settings.backfill_age_hours)),
        first_message_at=received,
        last_activity_at=received,
        closed_at=received if automated else None,
    )
    events.record(ticket, TicketEvent.Kind.CREATED, automated=automated, classification=verdict.classification)
    if related is not None:
        events.record(ticket, TicketEvent.Kind.RELATED, number=related.number, reason=_reason(rule))
        events.record(related, TicketEvent.Kind.RELATED, number=ticket.number, reason=_reason(rule))
    return ticket


def _reason(rule: str) -> str:
    return "follow-up after the ticket closed" if rule == "follow_up" else "same conversation"


def _attached(parsed: ParsedMessage, *, keep_text: bool) -> list[dict]:
    return [
        {
            "from": scrub_subject(item["from"]),
            "date": item["date"],
            "subject": scrub_subject(item["subject"]),
            "text": scrub_links(item["text"]) if keep_text else "",
        }
        for item in parsed.attached_messages
    ]


def _add_message(ticket, row, parsed, classified, settings, fingerprint) -> TicketMessage:
    verdict = classified.verdict
    own_mail = verdict.classification == "own"
    html, html_cut = (
        ("", False) if own_mail else sanitize_html(parsed.html, max_chars=int(settings.body_html_max_chars))
    )
    body_text = OWN_MAIL_NOTE if own_mail else scrub_links(parsed.text)
    text_cut = len(body_text) > int(settings.body_text_max_chars)
    message = TicketMessage.objects.create(
        ticket=ticket,
        kind=TicketMessage.Kind.AUTOMATED if classified.automated else TicketMessage.Kind.CUSTOMER,
        inbound=row,
        internet_message_id=(parsed.message_id or row.internet_message_id)[:255],
        in_reply_to=parsed.in_reply_to[:255],
        references=parsed.references[-MAX_REFERENCES:],
        conversation_id=row.conversation_id[:255],
        fingerprint=fingerprint,
        from_address=parsed.from_address[:254],
        from_name=scrub_subject(parsed.from_name),
        to_addresses=parsed.to[:MAX_PARTICIPANTS],
        cc_addresses=parsed.cc[:MAX_PARTICIPANTS],
        reply_to=parsed.reply_to[:254],
        subject=scrub_subject(parsed.subject),
        occurred_at=row.received_at,
        sent_at=parsed.sent_at,
        body_text=body_text[: int(settings.body_text_max_chars)],
        body_html=html,
        body_truncated=parsed.truncated or parsed.incomplete or html_cut or text_cut,
        attached_messages=[] if own_mail else _attached(parsed, keep_text=not classified.automated),
        auth_summary=classified.auth,
        scam_level=classified.scam_level,
        classification=verdict.classification,
        subtype=verdict.subtype,
        signals=list(dict.fromkeys((*verdict.signals, *verdict.hints)))[:20],
    )
    if not own_mail:
        values = attachments.prepare(parsed.attachments, settings, truncated=parsed.truncated)
        TicketAttachment.objects.bulk_create([TicketAttachment(message=message, **item) for item in values])
    return message


def _joined(ticket: Ticket, message: TicketMessage, classified: Classified, rule: str, own) -> None:
    if classified.automated:
        events.record(ticket, TicketEvent.Kind.AUTOMATED_MESSAGE, **{"from": message.from_address, "rule": rule})
        return
    seen = [message.from_address, message.reply_to, *message.to_addresses, *message.cc_addresses]
    updates = {
        "participants": _participants([*ticket.participants, *seen], own),
        "unread": True,
        "last_activity_at": max(ticket.last_activity_at, message.occurred_at),
        "updated_at": timezone.now(),
    }
    events.record(ticket, TicketEvent.Kind.CUSTOMER_MESSAGE, **{"from": message.from_address, "rule": rule})
    if rule == "reopened":
        updates.update(status=Status.OPEN, closed_at=None, resolved_at=None)
        events.record(ticket, TicketEvent.Kind.REOPENED, reason="the customer replied", **_move(ticket.status))
    elif ticket.status == Status.PENDING_CUSTOMER:
        updates["status"] = Status.OPEN
        events.record(ticket, TicketEvent.Kind.STATUS, reason="the customer replied", **_move(ticket.status))
    if rule == "flood":
        updates["flags"] = list(dict.fromkeys([*ticket.flags, "flood"]))
        events.record(ticket, TicketEvent.Kind.FLOOD, **{"from": message.from_address})
    Ticket.objects.filter(pk=ticket.pk).update(**updates)


def _move(status: str) -> dict:
    return {"from": status, "to": Status.OPEN}
