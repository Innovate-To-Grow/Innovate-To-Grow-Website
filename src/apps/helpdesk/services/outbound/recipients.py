"""Whom a reply may go to, copy and quote, beyond the requester: their other addresses, and the addresses a reply never
copies (a relay that wrote for someone else, a no-reply address, a mailing list: ``ingest.routing.people``)."""

from apps.core.services.email.inbound.classification.rules import NOREPLY_RE

from ...models import Ticket, TicketMessage
from ..ingest.routing.people import same_person


def ticket_lists(ticket: Ticket) -> set[str]:
    """The mailing lists the ticket's mail came through: a reply never goes to one (it would reach all its members)."""
    found = TicketMessage.objects.filter(ticket=ticket).exclude(list_address="").values_list("list_address", flat=True)
    return {address.lower() for address in found}


def requester_addresses(ticket: Ticket) -> set[str]:
    """The requester's addresses on ``ticket``: theirs, and a sender that wrote for them under their own name (their
    other address); never a relay's."""
    addresses = {ticket.requester_email.lower()}
    spoke = TicketMessage.objects.filter(ticket=ticket, on_behalf_of__iexact=ticket.requester_email)
    for address, name, behalf_name in spoke.values_list("from_address", "from_name", "on_behalf_name"):
        if same_person(name, behalf_name):
            addresses.add(address.lower())
    return addresses


def cc_suggestions(ticket: Ticket) -> list[str]:
    """Participants a reply may copy: people only, so neither the requester, nor a relay that wrote for someone
    else (a web form), nor a no-reply address or a mailing list."""
    relays = TicketMessage.objects.filter(ticket=ticket, on_behalf_of__iexact=ticket.requester_email)
    skip = requester_addresses(ticket) | ticket_lists(ticket)
    for address, name, behalf_name in relays.values_list("from_address", "from_name", "on_behalf_name"):
        if not same_person(name, behalf_name):
            skip.add(address.lower())
    found = (str(item).lower() for item in ticket.participants or [])
    return [item for item in found if item not in skip and not NOREPLY_RE.match(item.partition("@")[0])]
