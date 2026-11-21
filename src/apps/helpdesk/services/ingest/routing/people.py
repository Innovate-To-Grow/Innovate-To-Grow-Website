"""Whom a message speaks for, beyond its sender (``speaks_for``), kept on the message (``TicketMessage.on_behalf_of``,
``on_behalf_name``, ``list_address``).

- A web form (or another relay) sends what someone wrote from its own address and names that person in Reply-To: the
  first Reply-To address that is neither the sender, nor one of the site's own addresses, nor an address the message
  was sent To (a person asking for replies to their team), nor a mailing list's own address. A form that copies the
  submitter (Cc) still names them. That person is the requester of a new ticket (``pipeline.store``), every Reply-To
  address and the sender participants. As any mail program would, replies go to that person.
- A mailing list's own address (its List-Post; without one, the address its List-Id names, ``name@domain`` for
  ``name.domain``, else one list mail is sent To and either comes from or asks replies to) is never a requester. List
  mail speaks for its poster: the sender, or when the list rewrote the sender (Mailman's munged From, Google Groups:
  the From is the list) X-Original-From, else the Reply-To or Cc address that is not the list.
- A relay never threads as the people it relayed for (``matching``): one form's submissions do not join each other's
  tickets. A Reply-To naming the sender's other address under the same name (a person writing from work, asking for
  replies at home) speaks for the same person: both addresses are theirs. A Reply-To is not authenticated, so
  nothing automatic goes to it (``outbound.acknowledgement`` answers only an authenticated sender).
"""

import re
from dataclasses import dataclass

from apps.core.services.email.inbound.classification import headers

from ..reading.message import ParsedMessage

MAX_REPLY_TO = 10
_MAILTO_RE = re.compile(r"<\s*mailto:([^>?\s]+)", re.IGNORECASE)
_LIST_ID_RE = re.compile(r"<\s*([^<>\s]+)\s*>")
_WORD_RE = re.compile(r"\w+")


@dataclass(frozen=True)
class Speaker:
    address: str = ""  # whom the message speaks for, when not its sender
    name: str = ""
    list_address: str = ""  # the mailing list it came through


def reply_to_pairs(parsed: ParsedMessage) -> list[tuple[str, str]]:
    """``(name, address)`` of each address in the message's Reply-To."""
    return headers.addresses(headers.first(parsed.headers, "reply-to"), limit=MAX_REPLY_TO)


def _list_mail(parsed: ParsedMessage) -> bool:
    precedence = headers.first(parsed.headers, "precedence").strip().lower()
    return bool(headers.first(parsed.headers, "list-id").strip()) or precedence == "list"


def _list_id(parsed: ParsedMessage) -> str:
    value = headers.first(parsed.headers, "list-id").strip()
    found = _LIST_ID_RE.search(value)
    return (found.group(1) if found else value if " " not in value else "").lower()


def list_addresses(parsed: ParsedMessage) -> list[str]:
    """The mailing list's own addresses (List-Post's mailto, in the header's order). A list that gives none (an
    announcement list, "List-Post: NO") is known by its List-Id (``name.domain`` for ``name@domain``: Mailman, Google
    Groups, Sympa, LISTSERV), else by an address it is sent To that it comes from (the list rewrote its poster) or
    asks replies to; never a poster's own Reply-To (her other address)."""
    found = _MAILTO_RE.findall(headers.joined(parsed.headers, "list-post"))
    lists = list(dict.fromkeys(address.strip().lower() for address in found if "@" in address))
    if lists or not _list_mail(parsed):
        return lists
    replies = [address for _name, address in reply_to_pairs(parsed)]
    seen = list(dict.fromkeys([parsed.from_address, *parsed.to, *parsed.cc, *replies]))
    list_id = _list_id(parsed)
    named = [address for address in seen if list_id and list_id in (address, ".".join(address.split("@", 1)))]
    return named or [address for address in dict.fromkeys([parsed.from_address, *replies]) if address in parsed.to][:1]


def _words(name: str) -> list[str]:
    text = str(name or "").casefold()
    last, comma, first = text.partition(",")  # "Stone, Rhea" is Rhea Stone
    return _WORD_RE.findall(f"{first} {last}" if comma and first.strip() else text)


def same_person(name: str, other: str) -> bool:
    """Whether two display names are the same person's, as mail programs show one name differently ("Rhea",
    "Stone, Rhea", "Rhea Stone (Home)" are Rhea Stone): the words of one are among the other's, whatever their case,
    order and punctuation; a one-word name only as the other's first (an assistant "Kim" is not "Kai Kim")."""
    short, long = sorted((_words(name), _words(other)), key=len)
    if not short:
        return False
    return short[0] == long[0] if len(short) == 1 else set(short) <= set(long)


def speaks_for(parsed: ParsedMessage, own) -> Speaker:
    lists = list_addresses(parsed)
    listed = lists[0] if lists else ""
    skip = {parsed.from_address, *own, *lists, *parsed.to}
    if parsed.from_address in lists:  # a list rewrote its poster's address
        poster = headers.addresses(headers.first(parsed.headers, "x-original-from"), limit=1)
        cc = headers.addresses(headers.joined(parsed.headers, "cc"), limit=MAX_REPLY_TO)
        candidates = [*poster, *reply_to_pairs(parsed), *cc]
    elif _list_mail(parsed):  # posted by its sender: whatever the Reply-To, they are the person
        candidates = []
    else:
        candidates = reply_to_pairs(parsed)
    for name, address in candidates:
        if address and address not in skip:
            return Speaker(address, name, listed)
    return Speaker(list_address=listed)


def reply_to_person(parsed: ParsedMessage, own) -> tuple[str, str] | None:
    """``(name, address)`` of the person ``parsed`` speaks for instead of its sender, else None."""
    speaker = speaks_for(parsed, own)
    return (speaker.name, speaker.address) if speaker.address else None


def identity(parsed: ParsedMessage, own) -> str:
    """Whom a message is from when it threads by number or conversation: the person it speaks for, else its sender."""
    return speaks_for(parsed, own).address or parsed.from_address
