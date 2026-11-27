"""One page of a Gmail IMAP folder for the inbox list, read without downloading whole messages.

* The page is a slice of the folder's UIDs (one ``UID SEARCH``, numbers only): the newest ``limit`` below ``before``
  (the "Load older" cursor, ``paging``), or the newest ``limit`` of all.
* Each message of the page is fetched as its flags, its ``BODYSTRUCTURE`` (whether it has attachments), its header
  and the first ``LIST_TEXT_BYTES`` of its text, all with ``BODY.PEEK``: listing never sets ``\\Seen`` and never
  downloads attachments.
"""

import base64
import binascii
import email
import email.policy
import re
from typing import Any

from imap_tools import MailMessage
from imap_tools.errors import MailboxFetchError
from imap_tools.utils import check_command_status

# How much of a message's text is read for its snippet (the list shows about 200 characters).
LIST_TEXT_BYTES = 4096
LIST_PARTS = f"(UID FLAGS BODYSTRUCTURE BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.{LIST_TEXT_BYTES}>)"

_START = re.compile(rb"^\d+ \(")
_UID = re.compile(rb"\bUID (\d+)")
_FLAGS = re.compile(rb"\bFLAGS \(([^)]*)\)")
_LITERAL = re.compile(rb"(BODY\[(HEADER|TEXT)\](?:<\d+>)?) \{\d+\}$")
_ATTACHMENT = re.compile(rb'\("attachment"', re.IGNORECASE)


class PartialMessage:
    """What the list needs of a message, from its header and the start of its text, with the attributes of an
    ``imap_tools`` message that ``message_summary`` reads."""

    html = ""  # the snippet is made from ``text``, whichever part it came from

    def __init__(self, uid: str, flags: tuple, header: bytes, text: bytes, *, has_attachments: bool):
        parsed = MailMessage.from_bytes(header)
        self.uid = uid
        self.flags = flags
        self.has_attachments = has_attachments
        self.subject = parsed.subject
        self.from_values = parsed.from_values
        self.from_ = parsed.from_
        self.to_values = parsed.to_values
        self.date = parsed.date
        self.headers = dict(parsed.headers.items())
        self.text = _first_text(header + text)


def read_page(client, criteria, *, before: int | None, limit: int) -> list[PartialMessage]:
    """The newest ``limit`` messages matching ``criteria`` below UID ``before`` (None: from the newest), newest
    first."""
    uids = sorted({int(uid) for uid in client.uids(criteria) if str(uid).isdigit()})
    if before is not None:
        uids = [uid for uid in uids if uid < before]
    page = [str(uid) for uid in reversed(uids[-limit:])] if limit > 0 else []
    if not page:
        return []
    found = {message.uid: message for message in fetch_partial(client, page)}
    return [found[uid] for uid in page if uid in found]


def fetch_partial(client, uids: list[str]) -> list[PartialMessage]:
    """One ``UID FETCH`` of ``LIST_PARTS`` for ``uids`` (``client``: a logged-in ``imap_tools`` mailbox)."""
    result = client.client.uid("FETCH", ",".join(uids), LIST_PARTS)
    check_command_status(result, MailboxFetchError)
    return [message for message in (_message(item) for item in _split(result[1] or [])) if message is not None]


def _split(data: list) -> list[list]:
    """The FETCH response's items grouped per message: each message starts with ``<seq> (``."""
    messages: list[list] = []
    for item in data:
        head = item[0] if isinstance(item, tuple) else item
        if isinstance(head, bytes) and _START.match(head):
            messages.append([])
        if messages:
            messages[-1].append(item)
    return messages


def _message(items: list) -> PartialMessage | None:
    meta, sections = b"", {b"HEADER": b"", b"TEXT": b""}
    for item in items:
        if isinstance(item, tuple):
            prefix, literal = item[0] or b"", item[1] or b""
            meta += prefix
            match = _LITERAL.search(prefix)
            if match:
                sections[match.group(2)] = literal
            else:
                meta += literal  # a BODYSTRUCTURE string sent as a literal (an unusual file name)
        elif isinstance(item, bytes):
            meta += item
    uid = _UID.search(meta)
    if uid is None:
        return None
    flags = _FLAGS.search(meta)
    return PartialMessage(
        uid.group(1).decode(),
        tuple(flags.group(1).decode(errors="replace").split()) if flags else (),
        sections[b"HEADER"],
        sections[b"TEXT"],
        has_attachments=bool(_ATTACHMENT.search(meta)),
    )


def _first_text(raw: bytes) -> str:
    """The plain text of a (possibly cut-off) message, else its HTML: what its snippet is made of."""
    message = email.message_from_bytes(raw, policy=email.policy.compat32)
    found: dict[str, str] = {}
    for part in message.walk():
        subtype = part.get_content_type()
        if subtype in ("text/plain", "text/html") and subtype not in found:
            found[subtype] = _decoded(part)
    return found.get("text/plain") or found.get("text/html") or ""


def _decoded(part: Any) -> str:
    if str(part.get("Content-Transfer-Encoding", "")).strip().lower() == "base64":
        # The text was cut off mid-part: decode the whole base64 quanta (the email package gives up on the rest).
        raw = "".join(str(part.get_payload()).split())
        try:
            payload = base64.b64decode(raw[: len(raw) - len(raw) % 4])
        except (binascii.Error, ValueError):
            payload = b""
    else:
        payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")
