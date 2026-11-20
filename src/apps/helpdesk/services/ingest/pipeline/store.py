"""Storing one classified inbound message: on the ticket it belongs to, or on a new one.

The rules (Hongzhe's decision of 2026-11-11 on top of item2-helpdesk-bounces-plan §2.4):

- Every message is stored once (``fingerprint``); a second copy of it only marks the inbound row as a duplicate.
- Automated mail joins the ticket it threads to as a collapsed entry and changes nothing on it (no reopening, no
  unread mark, no new activity time). Otherwise it opens a ticket that is closed at once, ``automated`` (hidden from
  the default queue), with low priority; spam is closed as spam. Nothing is ever sent for it.
- A person's message (or an uncertain one) joins the ticket it threads to, unless that ticket is automated or spam:
  then it opens a new ticket linked to it. A ticket closed less than ``reopen_window_days`` before the message arrived
  reopens; an older one gets a linked follow-up ticket. A sender with more than ``flood_threshold`` new tickets within
  ``flood_window_minutes`` has the next one grouped into their latest open ticket, which is flagged (with none open,
  it opens a ticket of its own, so a person's message is never hidden in a closed one).
- The site's own messages keep no body or attachment (they may hold sign-in codes).
- A person's new ticket starts with medium impact and urgency (moderate priority) and, unless it is backfilled, its
  SLA clock (``tickets.sla``); automated mail starts low and has no clock. With sending on and the acknowledgement
  switched on, the requester is told the ticket number (``outbound.replies.queue_acknowledgement``).
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.models import InboundMessage
from apps.core.services.email.inbound import scrub_subject
from apps.mail.models import EmailCampaign

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ...outbound import replies
from ...tickets import events, numbering, priority, sla
from ..reading.message import ParsedMessage
from ..routing import matching
from ..routing.classify import Classified
from .messages import Status, _add_message, _joined, _participants


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
        reply = classified.site_reply
        if match.campaign_id is None and reply is not None and reply.campaign_id is not None:
            # A reply to a campaign email sent without a Message-ID (found by its sender and subject).
            match = replace(match, campaign_id=reply.campaign_id)
        ticket, created, rule = _target(match, parsed, classified, settings, row.received_at, own)
        message = _add_message(ticket, row, parsed, classified, settings, fingerprint)
        if not created:
            _joined(ticket, message, classified, rule, own)
        elif not classified.automated:
            replies.queue_acknowledgement(ticket, message, settings)
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
    # Only into a ticket still open: added to a closed one, a person's message would be hidden from the queue (it
    # neither reopens it nor shows under the default status filter). With none open, it opens a ticket of its own.
    open_tickets = recent.filter(status__in=Ticket.OPEN_STATUSES)
    return open_tickets.select_for_update().order_by("-first_message_at").first()


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
    impact, urgency = priority.AUTOMATED_DEFAULT if automated else priority.PERSON_DEFAULT
    ticket_priority = priority.priority_for(impact, urgency)
    backfilled = timezone.now() - received > timedelta(hours=int(settings.backfill_age_hours))
    clock = {} if automated or backfilled else sla.start_values(ticket_priority, received)
    ticket = numbering.create_ticket(
        subject=scrub_subject(parsed.subject) or "(no subject)",
        status=closed_status if automated else Status.NEW,
        priority=ticket_priority,
        impact=impact,
        urgency=urgency,
        **clock,
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
        backfilled=backfilled,
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
