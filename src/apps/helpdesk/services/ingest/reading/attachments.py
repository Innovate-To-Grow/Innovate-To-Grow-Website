"""Which attachments are stored, and how a stored one is offered for download.

Attachments live in PostgreSQL (``TicketAttachment.content``), never on the public media storage. Only metadata is
kept for: blocked file types (executables and scripts, disk images, active content such as HTML or SVG, macro-enabled
Office files, OneNote and CHM; an executable renamed to something harmless is caught by its content), files over the
per-file cap, files past the per-message total, and everything of a message cut off at the read limit (it may be
incomplete). A text file (declared ``text/*`` or named like one, and not a known binary format by its content) is
stored with its personal sign-in links replaced by ``[sign-in link removed]``, otherwise byte for byte; every other
file (PDF, Office documents, images, archives) is stored as received, so a link inside one is not removed. A saved
message (``.eml``) is never stored: it is read like a forwarded one (``mime``). Downloads are always
``Content-Disposition: attachment`` with ``X-Content-Type-Options: nosniff``, and ``application/octet-stream`` unless
the content is a raster image; archives are offered only after a warning.
"""

import codecs
import hashlib

from ....models import HelpdeskSettings, TicketAttachment
from ...tickets.working import scrub_sign_in_links
from .message import _PART_ERRORS, ParsedAttachment, text_codec

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
# Read as text also when sent as application/octet-stream (or as Excel, as Outlook sends a .csv).
TEXT_EXTENSIONS = frozenset(
    {
        "txt", "text", "log", "csv", "tsv", "htm", "html", "xhtml", "xml", "svg", "json", "ics", "vcf", "md",
        "markdown", "rtf", "yaml", "yml",
    }
)  # fmt: skip
_UTF16_BOMS = ((codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"))


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
            # Staff download what is stored: a text file must not hand them the requester's sign-in link.
            content = scrub_text_file(item.data, item.charset) if is_text_file(item, detected) else item.data
            stored_total += item.size
        kept = item.data if content is None else content  # a stored file's size and hash are those of what is stored
        rows.append(
            {
                "filename": item.filename[:255],
                "declared_type": item.content_type[:127],
                "detected_type": detected,
                "size": item.size if content is None else len(content),
                "sha256": hashlib.sha256(kept).hexdigest() if kept is not None else "",
                "is_inline": item.is_inline,
                "content_id": item.content_id[:255],
                "blocked": blocked,
                "not_stored_reason": reason,
                "content": content,
            }
        )
    return rows


def is_text_file(item: ParsedAttachment, detected: str) -> bool:
    """Declared ``text/*`` or named like a text file, unless its content is a known binary format (``detected``)."""
    return not detected and (item.content_type.startswith("text/") or extension(item.filename) in TEXT_EXTENSIONS)


def scrub_text_file(data: bytes, charset: str = "") -> bytes:
    """A text file with its personal sign-in links replaced, read and written back with the same codec (``_codec``):
    ``surrogateescape`` keeps the bytes it cannot read as they were, and a file without such a link is returned as
    it came."""
    codec = _codec(data, charset)
    for errors in ("surrogateescape", "replace"):
        try:
            return _scrubbed(data, codec, errors)
        except _PART_ERRORS:
            pass
    return _scrubbed(data, "utf-8", "surrogateescape")  # reads and writes back any bytes


def _scrubbed(data: bytes, codec: str, errors: str) -> bytes:
    text = data.decode(codec, errors)
    scrubbed = scrub_sign_in_links(text)
    return data if scrubbed == text else scrubbed.encode(codec, errors)


def _codec(data: bytes, charset: str) -> str:
    """A UTF-16 byte order mark (then kept as the text's first character), else the declared charset, else UTF-8."""
    marked = next((codec for mark, codec in _UTF16_BOMS if data.startswith(mark)), "")
    return marked or text_codec(charset)


def needs_warning(attachment: TicketAttachment, settings: HelpdeskSettings) -> bool:
    """Archives (by name or content) are downloaded only after a warning: their contents cannot be inspected."""
    return extension(attachment.filename) in settings.warn_extension_set or attachment.detected_type in ARCHIVE_TYPES


def download_content_type(attachment: TicketAttachment) -> str:
    return attachment.detected_type if attachment.detected_type in RASTER_TYPES else "application/octet-stream"
