"""Who a message speaks for, beyond its sender.

A web form (or another relay) sends what someone wrote from its own address and names that person in Reply-To. A
person's message whose Reply-To is one address that is neither its sender nor one of the site's own asks for replies
to go there, as any mail program would send them: that person is the requester of a new ticket
(``pipeline.store``) and the sender a participant. A Reply-To is not authenticated, so nothing automatic goes to it
(``outbound.acknowledgement`` answers only an authenticated sender).
"""

from apps.core.services.email.inbound.classification import headers

from ..reading.message import ParsedMessage


def reply_to_person(parsed: ParsedMessage, own) -> tuple[str, str] | None:
    """``(name, address)`` of the one person ``parsed`` asks replies to go to instead of its sender, else None."""
    pairs = headers.addresses(headers.first(parsed.headers, "reply-to"), limit=2)
    if len(pairs) != 1:
        return None
    name, address = pairs[0]
    if not address or address == parsed.from_address or address in own:
        return None
    return name, address
