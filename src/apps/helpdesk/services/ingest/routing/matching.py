"""Finding the ticket an inbound message belongs to (item2-helpdesk-bounces-plan §2.4).

Tried in order; the first that finds a ticket wins:

1. ``In-Reply-To`` / ``References`` naming a message already on a ticket. A reply to a campaign email names an
   outgoing email (``OutboundEmail``) instead: it finds no ticket, and the new ticket is linked to that campaign.
2. The subject token ``[I2G-#1234]`` (also without brackets), only from a participant of that ticket: anyone can
   type a number, so a stranger's mention opens a new ticket that notes it. The participant is the person the
   message speaks for (``people``) or its sender: someone who answers under the ticket's number wrote on it before,
   or was copied, whatever Reply-To they add (an assistant, a team mailbox, their other address). A relay (below)
   that is not the requester counts only for itself: a web form's submission for someone new never joins a ticket
   the form opened, as anyone can type that ticket's number into the form.
3. Microsoft Graph's ``conversationId``, again only for a participant: a fallback, as Microsoft can change it when an
   outsider replies, and every reply to one blast may share it (one form's submissions share one subject). So a relay
   is no participant here: an address that wrote on the ticket for someone under another name (a web form), or that
   writes now under another name than when it did (a form naming each submitter), unless it is the requester's;
   and a message that speaks for someone else threads this way only as that person. One form's submissions never
   join each other's tickets.

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


def requesters_of(ticket: Ticket) -> set[str]:
    """The requester's addresses: theirs, and every address of the member the ticket belongs to."""
    addresses = {ticket.requester_email.lower()}
    if ticket.requester_member_id:
        member_addresses = ContactEmail.objects.filter(member_id=ticket.requester_member_id)
        addresses |= {address.lower() for address in member_addresses.values_list("email_address", flat=True)}
    return addresses - {""}


def participants_of(ticket: Ticket) -> set[str]:
    """Who may thread into a ticket by its token or conversation: its requester's addresses and every address seen
    on it."""
    return ({str(item).lower() for item in ticket.participants or ()} | requesters_of(ticket)) - {""}


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


def _relays(ticket: Ticket, sender: str, sender_name: str) -> set[str]:
    """Addresses that wrote on ``ticket`` for someone under another name (a web form), and ``sender`` when it wrote
    there for someone under another name than it writes under now (a form naming each submitter)."""
    found = set()
    relayed = TicketMessage.objects.filter(ticket=ticket, kind__in=TicketMessage.INBOUND_KINDS).exclude(on_behalf_of="")
    for address, name, behalf_name in relayed.values_list("from_address", "from_name", "on_behalf_name"):
        address = address.lower()
        if not people.same_person(name, behalf_name) or (
            address == sender and not people.same_person(name, sender_name)
        ):
            found.add(address)
    return found


def _answers(ticket: Ticket, person: str, sender: str, name: str) -> bool:
    """Whether a message under ``ticket``'s number is from someone on it: the person it speaks for, or its sender,
    unless the sender is a relay there speaking for someone new (a form's next submitter, not the requester)."""
    participants = participants_of(ticket)
    if person in participants:
        return True
    return sender in participants and (sender in requesters_of(ticket) or sender not in _relays(ticket, sender, name))


def _by_token(numbers: list[int], person: str, sender: str, name: str) -> tuple[Ticket | None, list[int]]:
    mentions = []
    for number in numbers:
        ticket = Ticket.objects.filter(number=number).first()
        if ticket is None:
            continue
        target = follow_merges(ticket)
        if _answers(target, person, sender, name):
            return target, mentions
        mentions.append(number)
    return None, mentions


def _by_conversation(conversation_id: str, person: str, sender: str, name: str, *, prefer_human: bool):
    ticket_ids = (
        TicketMessage.objects.filter(conversation_id=conversation_id)
        .order_by("-occurred_at")
        .values_list("ticket_id", flat=True)[: CANDIDATE_TICKETS * 5]
    )
    for ticket in _ranked(list(ticket_ids), prefer_human=prefer_human):
        if person in participants_of(ticket) - (_relays(ticket, sender, name) - requesters_of(ticket)):
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
    person, sender, name = people.identity(parsed, own), parsed.from_address, parsed.from_name
    ticket, mentions = _by_token(numbering.subject_numbers(parsed.subject), person, sender, name)
    if ticket is not None:
        return Match(ticket, "subject_token", campaign_id)
    if conversation_id:
        ticket = _by_conversation(conversation_id, person, sender, name, prefer_human=prefer_human)
        if ticket is not None:
            return Match(ticket, "conversation", campaign_id, tuple(mentions))
    return Match(None, "", campaign_id, tuple(mentions))
