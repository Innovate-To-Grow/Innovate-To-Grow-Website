"""Reading one inbound message from its raw MIME: envelope headers, bodies, attachments and attached messages.

Anyone can mail the mailbox, so the input is hostile. Headers are read with ``core``'s hardened helpers (``compat32``
parsing, every value cut to 998 characters before it is decoded); the MIME tree is walked to at most ``MAX_PARTS``
parts and ``MAX_DEPTH`` levels (a message is marked ``incomplete`` past them); each text part is decoded from at most
``TEXT_PART_MAX_BYTES``; attached messages (forwards, the original inside a bounce report, a saved ``.eml`` file
whatever type it is sent as) are read to a summary of their headers and text, never kept as raw bytes, and their own
attachments are ignored. A message cut off at the read limit (``truncated``) keeps what was read. NUL characters are
dropped from every text read (headers, bodies, part headers): PostgreSQL text cannot hold them, and a body that has
some (a UTF-16 part labelled as another charset is full of them) must still become a ticket. Nothing here touches
the database.
"""

from apps.core.services.email.inbound.classification import headers as mime
from apps.core.services.email.telemetry import text

from .message import ParsedMessage
from .mime import _Walker


def parse(raw: bytes, *, truncated: bool = False) -> ParsedMessage:
    message = mime.parse(raw)
    headers = mime.header_map(message)
    content_type, params = mime.content_type(message)
    parsed = ParsedMessage(
        headers=headers,
        truncated=truncated,
        content_type=content_type,
        report_type=params.get("report-type", "").strip().lower()[:64],
    )
    _read_envelope(parsed, headers)
    _Walker(parsed).walk(message, 0)
    return parsed


def _read_envelope(parsed: ParsedMessage, headers: dict) -> None:
    sender = mime.addresses(mime.first(headers, "from"), limit=1)
    parsed.from_name, parsed.from_address = sender[0] if sender else ("", "")
    parsed.to = [address for _name, address in mime.addresses(mime.joined(headers, "to"))]
    parsed.cc = [address for _name, address in mime.addresses(mime.joined(headers, "cc"))]
    reply_to = mime.addresses(mime.first(headers, "reply-to"), limit=1)
    parsed.reply_to = reply_to[0][1] if reply_to else ""
    parsed.subject = mime.decoded(mime.first(headers, "subject"))
    parsed.message_id = text.message_id(mime.first(headers, "message-id"))
    parsed.in_reply_to = text.message_id(mime.first(headers, "in-reply-to"))
    parsed.references = mime.message_ids(mime.joined(headers, "references"))
    parsed.date_header = text.clean(mime.first(headers, "date"), 64)
    parsed.sent_at = mime.date(mime.first(headers, "date"))
