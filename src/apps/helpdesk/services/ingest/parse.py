"""Reading one inbound message from its raw MIME: envelope headers, bodies, attachments and attached messages.

Anyone can mail the mailbox, so the input is hostile. Headers are read with ``core``'s hardened helpers (``compat32``
parsing, every value cut to 998 characters before it is decoded); the MIME tree is walked to at most ``MAX_PARTS``
parts and ``MAX_DEPTH`` levels (a message is marked ``incomplete`` past them); each text part is decoded from at most
``TEXT_PART_MAX_BYTES``; attached messages (forwards, the original inside a bounce report) are read to a summary of
their headers and text, never kept as raw bytes, and their own attachments are ignored. A message cut off at the
read limit (``truncated``) keeps what was read. Nothing here touches the database.
"""

import hashlib
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

from apps.core.services.email.inbound import headers as mime
from apps.core.services.email.telemetry import text

MAX_PARTS = 500
MAX_DEPTH = 12
MAX_ATTACHED_MESSAGES = 5
TEXT_PART_MAX_BYTES = 4 * 1024 * 1024
ATTACHED_TEXT_MAX_CHARS = 64 * 1024
HTML_TO_TEXT_MAX_CHARS = 256 * 1024
NESTED_TYPES = frozenset({"message/rfc822", "message/global"})
# Machine-readable parts of a report: the bounce processor reads them; they are neither body nor attachment here.
REPORT_PARTS = frozenset(
    {
        "message/delivery-status",
        "message/global-delivery-status",
        "message/disposition-notification",
        "message/global-disposition-notification",
        "text/rfc822-headers",
        "message/global-headers",
    }
)
BODY_TYPES = ("text/plain", "text/html")
_PART_ERRORS = (AssertionError, LookupError, TypeError, ValueError, UnicodeError, IndexError, AttributeError)


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    content_id: str = ""
    is_inline: bool = False
    data: bytes | None = None
    size: int = 0


@dataclass
class ParsedMessage:
    headers: dict
    message_id: str = ""
    in_reply_to: str = ""
    references: list = field(default_factory=list)
    subject: str = ""
    from_address: str = ""
    from_name: str = ""
    to: list = field(default_factory=list)
    cc: list = field(default_factory=list)
    reply_to: str = ""
    date_header: str = ""
    sent_at: datetime | None = None
    content_type: str = "text/plain"
    report_type: str = ""
    text: str = ""
    html: str = ""
    attachments: list = field(default_factory=list)
    attached_messages: list = field(default_factory=list)
    has_calendar: bool = False
    truncated: bool = False
    incomplete: bool = False

    def text_head(self, chars: int = 4096) -> str:
        return (self.text or html_to_text(self.html))[:chars]

    def fingerprint(self) -> str:
        """One message, however often it arrives: its Message-ID, or (none) its sender, date, subject and text."""
        if self.message_id:
            basis = f"message-id\n{self.message_id.lower()}"
        else:
            basis = "\n".join(
                ("content", self.from_address, self.date_header, text.normalize_subject(self.subject), self.text[:4096])
            )
        return hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()


def html_to_text(html: str, limit: int = HTML_TO_TEXT_MAX_CHARS) -> str:
    if not html:
        return ""
    return BeautifulSoup(html[:limit], "html.parser").get_text("\n").strip()


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


class _Counter:
    def __init__(self):
        self.parts = 0


class _Walker:
    """Walks one message's MIME tree into ``parsed``; attached messages share the part counter."""

    def __init__(self, parsed: ParsedMessage, counter: _Counter | None = None, *, nested: bool = False):
        self.parsed = parsed
        self.counter = counter or _Counter()
        self.nested = nested

    def walk(self, part, depth: int) -> None:
        if self.counter.parts >= MAX_PARTS or depth > MAX_DEPTH:
            self.parsed.incomplete = True
            return
        self.counter.parts += 1
        content_type = _content_type(part)
        if content_type in NESTED_TYPES:
            self._attached_message(part, depth)
        elif part.is_multipart():
            payload = part.get_payload()
            for sub in payload if isinstance(payload, list) else ():
                self.walk(sub, depth + 1)
        elif content_type not in REPORT_PARTS:
            self._leaf(part, content_type)

    def _leaf(self, part, content_type: str) -> None:
        if content_type == "text/calendar":
            self.parsed.has_calendar = True
        disposition = _disposition(part)
        filename = _filename(part)
        if content_type in BODY_TYPES and disposition != "attachment" and not filename:
            body = _decode_text(part)
            if content_type == "text/plain":
                self.parsed.text = f"{self.parsed.text}\n\n{body}" if self.parsed.text else body
            else:
                self.parsed.html = f"{self.parsed.html}\n{body}" if self.parsed.html else body
        elif not self.nested:
            self._attachment(part, content_type, disposition, filename)

    def _attachment(self, part, content_type: str, disposition: str, filename: str) -> None:
        try:
            data = part.get_payload(decode=True)
        except _PART_ERRORS:
            data = None
        data = data if isinstance(data, bytes) else None
        content_id = text.message_id(_header(part, "Content-ID"))
        number = len(self.parsed.attachments) + 1
        self.parsed.attachments.append(
            ParsedAttachment(
                filename=filename or f"attachment-{number}{mimetypes.guess_extension(content_type) or '.bin'}",
                content_type=content_type[:127],
                content_id=content_id,
                is_inline=disposition == "inline" or (bool(content_id) and disposition != "attachment"),
                data=data,
                size=len(data) if data is not None else 0,
            )
        )

    def _attached_message(self, part, depth: int) -> None:
        payload = part.get_payload()
        inner = payload[0] if isinstance(payload, list) and payload else None
        if inner is None or len(self.parsed.attached_messages) >= MAX_ATTACHED_MESSAGES:
            return
        headers = mime.header_map(inner)
        nested = ParsedMessage(headers=headers)
        _Walker(nested, self.counter, nested=True).walk(inner, depth + 1)
        self.parsed.incomplete = self.parsed.incomplete or nested.incomplete
        self.parsed.attached_messages.append(
            {
                "from": mime.decoded(mime.first(headers, "from"))[:255],
                "date": text.clean(mime.first(headers, "date"), 64),
                "subject": mime.decoded(mime.first(headers, "subject"))[:255],
                "text": (nested.text or html_to_text(nested.html))[:ATTACHED_TEXT_MAX_CHARS],
            }
        )


def _header(part, name: str) -> str:
    value = part.get(name)
    return str(value)[: mime.LIMIT] if value is not None else ""


def _content_type(part) -> str:
    try:
        return str(part.get_content_type()).lower()[:127]
    except _PART_ERRORS:
        return "application/octet-stream"


def _disposition(part) -> str:
    try:
        return str(part.get_content_disposition() or "").lower()
    except _PART_ERRORS:
        return ""


def _filename(part) -> str:
    try:
        name = part.get_filename()
    except _PART_ERRORS:
        name = None
    return clean_filename(mime.decoded(name)) if name else ""


def clean_filename(name: str) -> str:
    """A file name safe to show and to offer as a download: no directory part, no control characters."""
    base = text.clean(str(name or ""), 1000).replace("\\", "/").rsplit("/", 1)[-1].strip().lstrip(".")
    if len(base) > 255:
        stem, dot, extension = base.rpartition(".")
        base = f"{stem[: 250 - len(extension)]}.{extension}" if dot and len(extension) <= 16 else base[:255]
    return base


def _decode_text(part) -> str:
    try:
        payload = part.get_payload(decode=True)
    except _PART_ERRORS:
        return ""
    if not isinstance(payload, bytes):
        return ""
    payload = payload[:TEXT_PART_MAX_BYTES]
    try:
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
    except _PART_ERRORS:
        decoded = payload.decode("utf-8", errors="replace")
    return decoded.replace("\r\n", "\n").replace("\r", "\n")
