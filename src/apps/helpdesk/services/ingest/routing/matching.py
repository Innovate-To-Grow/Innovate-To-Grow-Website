"""Finding the ticket an inbound message belongs to (item2-helpdesk-bounces-plan §2.4).

Tried in order; the first that finds a ticket wins:

1. ``In-Reply-To`` / ``References`` naming a message already on a ticket. A reply to a campaign email names an
   outgoing email (``OutboundEmail``) instead: it finds no ticket, and the new ticket is linked to that campaign.
2. The subject token ``[I2G-#1234]`` (also without brackets), only from a participant of that ticket: anyone can
   type a number, so a stranger's mention opens a new ticket that notes it. The participant is the sender, or the
   person the message speaks for (``people``). A relay (an address that wrote, under another name, for the ticket's
   requester: a web form) is no participant there, so one form's submissions never join each other's tickets.
3. Microsoft Graph's ``conversationId``, again only for a participant: a fallback, as Microsoft can change it when an
   outsider replies, and every reply to one blast may share it (one form's submissions share one subject). A message
   that speaks for someone else threads this way only as that person.

A merged ticket is followed to the ticket it was merged into. Where several tickets qualify, a person's message
prefers one that is not automated (an earlier out-of-office reply of the same thread).
"""

import uuid
from dataclasses import dataclass

from apps.authn.models import ContactEmail
from apps.core.models import OutboundEmail

from ....models import Ticket, TicketMessage
from ...tickets import numbering
from ..reading.message import ParsedMessage
from . import people

MERGE_HOPS = 10
CANDIDATE_TICKETS = 20


@dataclass(frozen=True)
class Match:
    ticket: Ticket | None = None
    rule: str = ""
    campaign_id: uuid.UUID | None = None
    mentions: tuple[int, ...] = ()


def follow_merges(ticket: Ticket) -> Ticket:
    seen = set()
    while ticket.merged_into_id and ticket.pk not in seen and len(seen) < MERGE_HOPS:
        seen.add(ticket.pk)
        ticket = Ticket.objects.get(pk=ticket.merged_into_id)
    return ticket


def participants_of(ticket: Ticket) -> set[str]:
    """Who may thread into a ticket by its token or conversation: its requester, every address seen on it, and every
    address of the member it belongs to."""
    addresses = {str(item).lower() for item in ticket.participants or ()} | {ticket.requester_email.lower()}
    if ticket.requester_member_id:
        member_addresses = ContactEmail.objects.filter(member_id=ticket.requester_member_id)
        addresses |= {address.lower() for address in member_addresses.values_list("email_address", flat=True)}
    return addresses - {""}


def _ranked(ticket_ids, *, prefer_human: bool) -> list[Ticket]:
    tickets = [follow_merges(ticket) for ticket in Ticket.objects.filter(pk__in=set(ticket_ids))]
    tickets = list({ticket.pk: ticket for ticket in tickets}.values())
    tickets.sort(key=lambda ticket: ticket.last_activity_at, reverse=True)
    if prefer_human:
        tickets.sort(key=lambda ticket: ticket.automated or ticket.status == Ticket.Status.SPAM)
    return tickets


def _by_references(references: list[str], *, prefer_human: bool) -> Ticket | None:
    ticket_ids = (
        TicketMessage.objects.filter(internet_message_id__in=references)
        .order_by("-occurred_at")
        .values_list("ticket_id", flat=True)[:CANDIDATE_TICKETS]
    )
    ranked = _ranked(ticket_ids, prefer_human=prefer_human)
    return ranked[0] if ranked else None


def references_of(parsed: ParsedMessage) -> list[str]:
    """The Message-IDs a message names in In-Reply-To and References, unique, in order."""
    return [item for item in dict.fromkeys([*parsed.references, parsed.in_reply_to]) if item]


def _campaign(references: list[str]) -> uuid.UUID | None:
    email = (
        OutboundEmail.objects.filter(internet_message_id__in=references, campaign_id__isnull=False)
        .order_by("-created_at")
        .first()
    )
    return email.campaign_id if email is not None else None


def _may_thread(ticket: Ticket, person: str, sender: str, *, by_token: bool) -> bool:
    """Whether a message from ``sender``, speaking for ``person`` (the sender itself when for nobody else), may thread
    to ``ticket``. A relay is no participant: an address that wrote on it for its requester under another name, or for
    someone else than this message speaks for. A person's other address (the same name) stays theirs. By conversation
    a message speaking for someone else threads only as that person; by number, a requester answering with a Reply-To
    naming someone else (an assistant) threads too."""
    eligible = participants_of(ticket)
    relayed = TicketMessage.objects.filter(ticket=ticket, on_behalf_of__iexact=ticket.requester_email)
    for address, name, behalf_name in relayed.values_list("from_address", "from_name", "on_behalf_name"):
        if not people.same_person(name, behalf_name) or (person != sender and ticket.requester_email.lower() != person):
            eligible.discard(address.lower())
    if person in eligible:
        return True
    return by_token and person != sender and sender in eligible


def _by_token(numbers: list[int], person: str, sender: str) -> tuple[Ticket | None, list[int]]:
    mentions = []
    for number in numbers:
        ticket = Ticket.objects.filter(number=number).first()
        if ticket is None:
            continue
        target = follow_merges(ticket)
        if _may_thread(target, person, sender, by_token=True):
            return target, mentions
        mentions.append(number)
    return None, mentions


def _by_conversation(conversation_id: str, person: str, sender: str, *, prefer_human: bool):
    ticket_ids = (
        TicketMessage.objects.filter(conversation_id=conversation_id)
        .order_by("-occurred_at")
        .values_list("ticket_id", flat=True)[: CANDIDATE_TICKETS * 5]
    )
    for ticket in _ranked(list(ticket_ids), prefer_human=prefer_human):
        if _may_thread(ticket, person, sender, by_token=False):
            return ticket
    return None


def find(parsed: ParsedMessage, *, conversation_id: str = "", prefer_human: bool = True, own=frozenset()) -> Match:
    references = references_of(parsed)
    campaign_id = None
    if references:
        ticket = _by_references(references, prefer_human=prefer_human)
        if ticket is not None:
            return Match(ticket, "references")
        campaign_id = _campaign(references)
    person, sender = people.identity(parsed, own), parsed.from_address
    ticket, mentions = _by_token(numbering.subject_numbers(parsed.subject), person, sender)
    if ticket is not None:
        return Match(ticket, "subject_token", campaign_id)
    if conversation_id:
        ticket = _by_conversation(conversation_id, person, sender, prefer_human=prefer_human)
        if ticket is not None:
            return Match(ticket, "conversation", campaign_id, tuple(mentions))
    return Match(None, "", campaign_id, tuple(mentions))
