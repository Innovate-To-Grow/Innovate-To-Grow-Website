"""Whom a reply may go to, copy and quote, beyond the requester: their other addresses, and the addresses a reply never
copies (a relay that wrote for someone else, a no-reply address, a mailing list: ``ingest.routing.people``)."""

from apps.core.services.email.inbound.classification.rules import NOREPLY_RE

from ...models import Ticket, TicketMessage
from ..ingest.routing.people import same_person

INBOUND = TicketMessage.INBOUND_KINDS


def ticket_lists(ticket: Ticket) -> set[str]:
    """The mailing lists the ticket's mail came through: a reply never goes to one (it would reach all its members)."""
    found = TicketMessage.objects.filter(ticket=ticket).exclude(list_address="").values_list("list_address", flat=True)
    return {address.lower() for address in found}


def aliases(ticket: Ticket) -> dict[str, str]:
    """The requester's other addresses on ``ticket``, with their name: a sender that wrote for them under that name
    (work and home). A message from one counts as theirs only under that name (``replies.last_inbound``): a form that
    names each submitter writes for several people from one address."""
    spoke = TicketMessage.objects.filter(ticket=ticket, on_behalf_of__iexact=ticket.requester_email)
    return {
        address.lower(): name
        for address, name, behalf_name in spoke.values_list("from_address", "from_name", "on_behalf_name")
        if same_person(name, behalf_name)
    }


def requester_addresses(ticket: Ticket) -> set[str]:
    return {ticket.requester_email.lower(), *aliases(ticket)}


def theirs(message: TicketMessage, ticket: Ticket, other: dict[str, str]) -> bool:
    """Whether ``message`` is the requester's: from their address, written for them, or from another address of
    theirs (``other``: ``aliases``) only under their name: a form writing for several people under each one's."""
    address = message.from_address.lower()
    if address == ticket.requester_email.lower() or message.on_behalf_of.lower() == ticket.requester_email.lower():
        return True
    return address in other and same_person(message.from_name, other[address])


def writes_for_others(address: str) -> bool:
    """Whether ``address`` wrote for two or more people under another name (a web form): no person, even where it
    wrote as itself (a nameless submission). A person who once named an assistant wrote for one."""
    spoke = TicketMessage.objects.filter(kind__in=INBOUND, from_address__iexact=address).exclude(on_behalf_of="")
    people = set()
    for name, behalf, behalf_name in spoke.order_by().values_list("from_name", "on_behalf_of", "on_behalf_name"):
        if not same_person(name, behalf_name):
            people.add(behalf.lower())
            if len(people) > 1:
                return True
    return False


def cc_suggestions(ticket: Ticket) -> list[str]:
    """Participants a reply may copy: people only. A relay (an address that wrote on the ticket only for someone under
    another name, or one that writes for several people: a web form) is none; whoever wrote on the ticket as
    themselves, or was addressed by staff, is."""
    messages = TicketMessage.objects.filter(ticket=ticket)
    relayed = {
        address.lower()
        for address, name, behalf_name in messages.filter(kind__in=INBOUND)
        .exclude(on_behalf_of="")
        .values_list("from_address", "from_name", "on_behalf_name")
        if not same_person(name, behalf_name)
    }
    themselves = {
        item.lower()
        for item in messages.filter(kind__in=INBOUND, on_behalf_of="").values_list("from_address", flat=True)
    }
    themselves = {item for item in themselves if item not in relayed or not writes_for_others(item)}
    for to, cc in messages.filter(kind=TicketMessage.Kind.REPLY, automatic=False).values_list(
        "to_addresses", "cc_addresses"
    ):
        themselves.update(str(item).lower() for item in [*(to or ()), *(cc or ())])
    found = [str(item).lower() for item in ticket.participants or []]
    skip = requester_addresses(ticket) | ticket_lists(ticket) | (relayed - themselves)
    return [item for item in found if item not in skip and not NOREPLY_RE.match(item.partition("@")[0])]
