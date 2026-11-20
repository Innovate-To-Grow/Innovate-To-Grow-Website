"""Who a message speaks for, beyond its sender.

A web form (or another relay, or a mailing list rewriting its senders) sends what someone wrote from its own address
and names that person in Reply-To. A person's message whose Reply-To names someone who is neither its sender, nor
one of the site's own addresses, nor an address it was sent to (a list's own) asks for replies to go there, as any
mail program would send them: the first such person is the requester of a new ticket (``pipeline.store``), every
Reply-To address and the sender participants. It threads by number or conversation as that person (``identity``),
so a relay is never taken for the people it relays. A Reply-To is not authenticated, so nothing automatic goes to
it (``outbound.acknowledgement`` answers only an authenticated sender).
"""

from apps.core.services.email.inbound.classification import headers

from ..reading.message import ParsedMessage

MAX_REPLY_TO = 10


def reply_to_pairs(parsed: ParsedMessage) -> list[tuple[str, str]]:
    """``(name, address)`` of each address in the message's Reply-To."""
    return headers.addresses(headers.first(parsed.headers, "reply-to"), limit=MAX_REPLY_TO)


def reply_to_person(parsed: ParsedMessage, own) -> tuple[str, str] | None:
    """``(name, address)`` of the first person ``parsed`` asks replies to go to instead of its sender, else None."""
    sent_to = {*parsed.to, *parsed.cc}
    for name, address in reply_to_pairs(parsed):
        if address and address != parsed.from_address and address not in own and address not in sent_to:
            return name, address
    return None


def identity(parsed: ParsedMessage, own) -> str:
    """Whom a message is from when it threads by number or conversation: the person a relay names, else its sender."""
    person = reply_to_person(parsed, own)
    return person[1] if person else parsed.from_address
