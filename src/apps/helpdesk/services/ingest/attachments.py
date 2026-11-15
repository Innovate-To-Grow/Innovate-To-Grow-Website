"""Which attachments are stored, and how a stored one is offered for download.

Attachments live in PostgreSQL (``TicketAttachment.content``), never on the public media storage. Only metadata is
kept for: blocked file types (executables and scripts, disk images, active content such as HTML or SVG, macro-enabled
Office files, OneNote and CHM; an executable renamed to something harmless is caught by its content), files over the
per-file cap, files past the per-message total, and everything of a message cut off at the read limit (it may be
incomplete). Downloads are always ``Content-Disposition: attachment`` with ``X-Content-Type-Options: nosniff``, and
``application/octet-stream`` unless the content is a raster image; archives are offered only after a warning.
"""

import hashlib

from ...models import HelpdeskSettings, TicketAttachment
from .parse import ParsedAttachment

# Leading bytes of the formats worth recognising (the declared type and the file name are the sender's claim).
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"Rar!\x1a\x07", "application/vnd.rar"),
    (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
    (b"\x1f\x8b", "application/gzip"),
    (b"MZ", "application/x-msdownload"),
    (b"\x7fELF", "application/x-executable"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/x-ole-storage"),
)
RASTER_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
EXECUTABLE_TYPES = frozenset({"application/x-msdownload", "application/x-executable"})
ARCHIVE_TYPES = frozenset({"application/zip", "application/vnd.rar", "application/x-7z-compressed", "application/gzip"})


def sniff(data: bytes | None) -> str:
    if not data:
        return ""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return next((kind for signature, kind in _SIGNATURES if data.startswith(signature)), "")


def extension(filename: str) -> str:
    stem, dot, suffix = str(filename or "").rpartition(".")
    return suffix.strip().lower() if dot and stem else ""


def _megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


def prepare(items: list[ParsedAttachment], settings: HelpdeskSettings, *, truncated: bool) -> list[dict]:
    """The ``TicketAttachment`` values of a message's attachments: content for those that may be stored, the reason
    for those that may not."""
    blocked_types = settings.blocked_extension_set
    message_cap = int(settings.message_max_bytes)
    stored_total = 0
    rows = []
    for item in items:
        detected = sniff(item.data)
        blocked = extension(item.filename) in blocked_types or detected in EXECUTABLE_TYPES
        reason, content = "", None
        if blocked:
            reason = "Blocked file type: only its name, size and type are kept. Open the message in Outlook if needed."
        elif truncated:
            reason = "Not stored: the message was larger than the read limit, so this file may be incomplete."
        elif item.data is None:
            reason = "Not stored: the file could not be decoded."
        elif item.size > settings.attachment_max_bytes:
            reason = f"Not stored: larger than {_megabytes(settings.attachment_max_bytes)}; open it in Outlook."
        elif stored_total + item.size > message_cap:
            reason = "Not stored: the message's files together exceed the per-message limit; open it in Outlook."
        else:
            content = item.data
            stored_total += item.size
        rows.append(
            {
                "filename": item.filename[:255],
                "declared_type": item.content_type[:127],
                "detected_type": detected,
                "size": item.size,
                "sha256": hashlib.sha256(item.data).hexdigest() if item.data is not None else "",
                "is_inline": item.is_inline,
                "content_id": item.content_id[:255],
                "blocked": blocked,
                "not_stored_reason": reason,
                "content": content,
            }
        )
    return rows


def needs_warning(attachment: TicketAttachment, settings: HelpdeskSettings) -> bool:
    """Archives (by name or content) are downloaded only after a warning: their contents cannot be inspected."""
    return extension(attachment.filename) in settings.warn_extension_set or attachment.detected_type in ARCHIVE_TYPES


def download_content_type(attachment: TicketAttachment) -> str:
    return attachment.detected_type if attachment.detected_type in RASTER_TYPES else "application/octet-stream"
