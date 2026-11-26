"""Walking a message's MIME parts: bodies, attachments and attached messages (forwarded parts, saved ``.eml`` files),
within the limits."""

import mimetypes

from apps.core.services.email.inbound.classification import headers as mime
from apps.core.services.email.telemetry import text

from .message import (
    _PART_ERRORS,
    ATTACHED_TEXT_MAX_CHARS,
    BODY_TYPES,
    MAX_ATTACHED_MESSAGES,
    MAX_DEPTH,
    MAX_PARTS,
    MESSAGE_FILE_SUFFIXES,
    NESTED_TYPES,
    REPORT_PARTS,
    TEXT_PART_MAX_BYTES,
    ParsedAttachment,
    ParsedMessage,
    text_codec,
)
from .sanitize import html_text
from .tree import parse_mime


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
            self._leaf(part, content_type, depth)

    def _leaf(self, part, content_type: str, depth: int) -> None:
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
        elif filename.lower().endswith(MESSAGE_FILE_SUFFIXES):
            self._attached_message(part, depth, as_file=True)
        elif not self.nested:  # an attached message's own attachments are ignored
            self._attachment(part, content_type, disposition, filename)

    def _attachment(self, part, content_type: str, disposition: str, filename: str) -> None:
        data = _payload(part)
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
                charset=_charset(part),
            )
        )

    def _attached_message(self, part, depth: int, *, as_file: bool = False) -> None:
        if self.nested:  # a message attached inside an attached one is not read: the card counts it as not shown
            self.parsed.attached_dropped += 1
            return
        inner = (
            None
            if len(self.parsed.attached_messages) >= MAX_ATTACHED_MESSAGES
            else (_file_message(part) if as_file else _inner_message(part))
        )
        if inner is None:
            self.parsed.attached_dropped += 1  # past the limit, or not readable: the card says so (Outlook has it)
            return
        headers = mime.header_map(inner)
        nested = ParsedMessage(headers=headers)
        _Walker(nested, self.counter, nested=True).walk(inner, depth + 1)
        self.parsed.incomplete = self.parsed.incomplete or nested.incomplete
        self.parsed.attached_dropped += nested.attached_dropped
        self.parsed.attached_messages.append(
            {
                "from": mime.decoded(mime.first(headers, "from"))[:255],
                "date": text.clean(mime.first(headers, "date"), 64),
                "subject": mime.decoded(mime.first(headers, "subject"))[:255],
                "text": (nested.text or html_text(nested.html))[:ATTACHED_TEXT_MAX_CHARS],
            }
        )


def _inner_message(part):
    """The message an attached message part holds. One sent base64 or quoted-printable (RFC 2046 forbids it, yet
    Python's email library writes it) was kept as its encoded text (see ``tree``): it is read like a saved .eml file
    from its decoded bytes, and is not readable (counted on the card) when they hold no header."""
    payload = part.get_payload()
    if isinstance(payload, list):
        return payload[0] if payload else None
    message = _file_message(part)
    return message if message is not None and message.keys() else None


def _file_message(part):
    """The message saved in an attached file (an .eml), read from its decoded bytes like the outer message."""
    data = _payload(part)
    try:
        return parse_mime(data) if data else None
    except _PART_ERRORS:
        return None


def _payload(part) -> bytes | None:
    try:
        data = part.get_payload(decode=True)
    except _PART_ERRORS:
        return None
    return data if isinstance(data, bytes) else None


def _header(part, name: str) -> str:
    value = part.get(name)
    return str(value)[: mime.LIMIT].replace("\x00", "") if value is not None else ""


def _content_type(part) -> str:
    try:
        return str(part.get_content_type()).lower().replace("\x00", "")[:127]
    except _PART_ERRORS:
        return "application/octet-stream"


def _disposition(part) -> str:
    try:
        return str(part.get_content_disposition() or "").lower()
    except _PART_ERRORS:
        return ""


def _charset(part) -> str:
    try:
        return str(part.get_content_charset() or "")[:64]
    except _PART_ERRORS:
        return ""


def _filename(part) -> str:
    try:
        name = part.get_filename()
    except _PART_ERRORS:
        name = None
    return clean_filename(mime.decoded(name)) if name else ""


def clean_filename(name: str) -> str:
    """A file name safe to show and to offer as a download: no directory part, no control characters, and no dots
    or spaces at either end. Windows drops trailing ones when it saves a file, so "evil.js." would be saved as
    "evil.js": the blocked file types are checked on the name as it will be saved."""
    base = text.clean(str(name or ""), 1000).replace("\\", "/").rsplit("/", 1)[-1].strip(" .")
    if len(base) > 255:
        stem, dot, extension = base.rpartition(".")
        base = f"{stem[: 250 - len(extension)]}.{extension}" if dot and len(extension) <= 16 else base[:255]
    return base.rstrip(" .")


def _decode_text(part) -> str:
    payload = _payload(part)
    if payload is None:
        return ""
    payload = payload[:TEXT_PART_MAX_BYTES]
    try:
        decoded = payload.decode(text_codec(part.get_content_charset() or ""), errors="replace")
    except _PART_ERRORS:
        decoded = payload.decode("utf-8", errors="replace")
    return decoded.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
