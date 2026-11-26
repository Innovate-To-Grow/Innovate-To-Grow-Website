"""Who is on a ticket, for threading a message into it by its number or conversation (``matching``): the requester's
addresses, every address seen on it, the relays that wrote on it for others (a web form), and whether a message's
sender or the person it speaks for answers on it."""

from apps.authn.models import ContactEmail

from ....models import Ticket, TicketMessage
from . import people


def requesters_of(ticket: Ticket) -> set[str]:
    """The requester's addresses: theirs, and every verified address of the member the ticket belongs to (anyone can
    add an address to their account; until its code is entered it may be someone else's)."""
    addresses = {ticket.requester_email.lower()}
    if ticket.requester_member_id:
        member_addresses = ContactEmail.objects.filter(member_id=ticket.requester_member_id, verified=True)
        verified = {address.lower() for address in member_addresses.values_list("email_address", flat=True)}
        if addresses & verified:
            return addresses | verified
        # Intake can link a member by the verified sender of their same-name Reply-To.
        # Older tickets could instead have been linked by an unverified contact.
        opening = (
            ticket.messages.filter(kind__in=TicketMessage.INBOUND_KINDS).order_by("occurred_at", "created_at").first()
        )
        if (
            opening
            and opening.from_address.lower() in verified
            and opening.on_behalf_of.lower() == ticket.requester_email.lower()
            and opening.on_behalf_of
            and people.same_person(opening.from_name, opening.on_behalf_name)
        ):
            addresses |= verified
    return addresses - {""}


def participants_of(ticket: Ticket) -> set[str]:
    """Who may thread into a ticket by its token or conversation: its requester's addresses and every address seen
    on it."""
    return ({str(item).lower() for item in ticket.participants or ()} | requesters_of(ticket)) - {""}


def relays(ticket: Ticket, sender: str, sender_name: str) -> set[str]:
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


def _writes_for_others(address: str, participants: set[str], name: str) -> bool:
    """Whether ``address`` wrote for two or more other people who are not on the ticket: named under another name
    than its own (a web form's submitters), or under another name than it writes under now (a form writing under
    each submitter's name). Its own other addresses (its name, or none) never count, nor people on the ticket."""
    spoke = TicketMessage.objects.filter(kind__in=TicketMessage.INBOUND_KINDS, from_address__iexact=address)
    rows = spoke.exclude(on_behalf_of="").exclude(on_behalf_of__in=participants).order_by()
    people_off = set()
    for from_name, behalf, behalf_name in rows.values_list("from_name", "on_behalf_of", "on_behalf_name").distinct():
        named_other = bool(behalf_name) and not people.same_person(from_name, behalf_name)
        renamed = bool(from_name and name) and not people.same_person(from_name, name)
        if named_other or renamed:
            people_off.add(behalf.lower())
            if len(people_off) > 1:
                return True
    return False


def answers(ticket: Ticket, person: str, sender: str, name: str, person_name: str) -> bool:
    """Whether a message under ``ticket``'s number is from someone on it: the person it speaks for, or its sender,
    unless it speaks for someone new and the sender writes for other people or is a relay there (a form's next
    submitter), not the requester. The requester naming her own other address (under her name) always is."""
    participants = participants_of(ticket)
    if person in participants:
        return True
    if sender not in participants:
        return False
    requester = sender in requesters_of(ticket)
    if requester and people.same_person(name, person_name) and people.same_person(name, ticket.requester_name):
        return True  # her other address, under the name the ticket knows her by (not a form writing as each person)
    if _writes_for_others(sender, participants, name):
        return False
    return requester or sender not in relays(ticket, sender, name)
