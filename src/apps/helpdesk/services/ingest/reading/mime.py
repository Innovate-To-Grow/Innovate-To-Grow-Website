"""Walking a message's MIME parts: bodies, attachments and attached messages, within the limits."""

import mimetypes

from apps.core.services.email.inbound import headers as mime
from apps.core.services.email.telemetry import text

from .message import (
    _PART_ERRORS,
    ATTACHED_TEXT_MAX_CHARS,
    BODY_TYPES,
    MAX_ATTACHED_MESSAGES,
    MAX_DEPTH,
    MAX_PARTS,
    NESTED_TYPES,
    REPORT_PARTS,
    TEXT_PART_MAX_BYTES,
    ParsedAttachment,
    ParsedMessage,
    html_to_text,
)


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
    return decoded.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
