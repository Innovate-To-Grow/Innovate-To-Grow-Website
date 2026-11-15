"""Reading a bounce report (an Exchange NDR, or any RFC 3464 delivery status notification) from raw MIME.

Only what a bounce record needs is taken: per recipient its address, action, enhanced status code, diagnostic code
and remote server; per report the reporting server, its date, its own Message-ID, and the original message's
Message-ID and subject (from the returned headers or message, else the report's In-Reply-To and subject). A report
without a delivery-status part (an old-style bounce) is recognised by its sender or ``X-Failed-Recipients``; then
only the line of its text that carries a status code is read. Nothing else of the report is kept.

Anyone can mail the sending mailbox, so the input is hostile: it is parsed with the ``compat32`` policy (headers
stay plain strings until read), every header is cut to 998 characters before it is decoded or parsed, at most
``max_recipients`` recipients are read, and texts are read only up to a bound. The work stays linear in the input.
"""

import email
import email.policy
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from email.parser import HeaderParser
from email.utils import parsedate_to_datetime

from ..telemetry import text

STATUS_RE = re.compile(r"(?<![\d.])([245])\.(\d{1,3})\.(\d{1,3})(?![\d.])")
_TYPE_PREFIX_RE = re.compile(r"^\s*[A-Za-z0-9-]{1,32}\s*;\s*")
_REPORT_SUBJECT_RE = re.compile(
    r"^\s*(?:undeliverable|undelivered mail returned to sender|delivery status notification(?: \([a-z]+\))?|"
    r"delivery (?:has failed|delayed|failure)|returned mail|failure notice|delayed|mail delivery failed)\s*:\s*",
    re.IGNORECASE,
)
_REPORT_SENDERS = ("postmaster", "mailer-daemon", "mail-daemon", "maildaemon")
# How much of an old-style bounce's text, or of a returned-headers part, is read.
_TEXT_SCAN_LIMIT = 64 * 1024
LIMIT = text.HEADER_LIMIT


@dataclass(frozen=True)
class RecipientReport:
    recipient: str
    action: str = ""
    status: str = ""
    diagnostic: str = ""
    remote_mta: str = ""
    last_attempt_at: datetime | None = None


@dataclass(frozen=True)
class BounceReport:
    recipients: tuple[RecipientReport, ...]
    reporting_mta: str = ""
    arrival_at: datetime | None = None
    report_message_id: str = ""
    original_message_id: str = ""
    original_subject: str = ""
    structured: bool = False


def parse_report(raw: bytes, *, subject_hint: str = "", max_recipients: int = 50) -> BounceReport | None:
    """The report in ``raw``, or None when it is not a bounce report (say, a person's email that only mentions one).
    Only its first ``max_recipients`` recipients are read."""
    message = email.message_from_bytes(raw, policy=email.policy.compat32)
    original = _original_headers(message)
    common = {
        "report_message_id": text.message_id(_raw(message, "Message-ID")),
        "original_message_id": text.message_id(_raw(original, "Message-ID"))
        or text.message_id(_raw(message, "In-Reply-To")),
        "original_subject": _decoded(original, "Subject")
        or strip_report_prefix(_decoded(message, "Subject") or subject_hint[:LIMIT]),
    }
    status_part = _first_part(message, "message/delivery-status")
    if status_part is not None:
        reporting_mta, arrival_at, recipients = _status_blocks(status_part, max_recipients)
        return BounceReport(recipients, reporting_mta, arrival_at, structured=True, **common)
    failed = text.addresses(_raw(message, "X-Failed-Recipients", 4 * LIMIT).split(",")[:max_recipients])
    if not failed and not _from_report_sender(message):
        return None
    status, diagnostic = _status_line(message)
    recipients = tuple(RecipientReport(item, "failed", status, diagnostic) for item in failed) or (
        RecipientReport("", "failed" if status else "", status, diagnostic),
    )
    return BounceReport(recipients, arrival_at=_date(_raw(message, "Date")), **common)


def strip_report_prefix(subject: str) -> str:
    """The original subject inside a report subject such as "Undeliverable: <subject>"."""
    return _REPORT_SUBJECT_RE.sub("", str(subject or ""), count=1).strip()


def _status_blocks(part, max_recipients: int) -> tuple[str, datetime | None, tuple[RecipientReport, ...]]:
    blocks = part.get_payload()
    if not isinstance(blocks, list) or not blocks:
        return "", None, ()
    per_message = blocks[0]
    reporting_mta = text.clean(_strip_type(_raw(per_message, "Reporting-MTA")), 255)
    recipients = tuple(_recipient_report(block) for block in blocks[1 : 1 + max(1, max_recipients)])
    return reporting_mta, _date(_raw(per_message, "Arrival-Date")), recipients


def _recipient_report(block) -> RecipientReport:
    original = text.address(_strip_type(_raw(block, "Original-Recipient")))
    diagnostic = text.clean(_strip_type(_raw(block, "Diagnostic-Code")), 1000)
    status = _status_code(_raw(block, "Status")) or _status_code(diagnostic)
    return RecipientReport(
        recipient=original or text.address(_strip_type(_raw(block, "Final-Recipient"))),
        action=text.clean(_raw(block, "Action"), 16).lower(),
        status=status,
        diagnostic=diagnostic,
        remote_mta=text.clean(_strip_type(_raw(block, "Remote-MTA")), 255),
        last_attempt_at=_date(_raw(block, "Last-Attempt-Date")),
    )


def _status_code(value) -> str:
    match = STATUS_RE.search(str(value or ""))
    return ".".join(match.groups()) if match else ""


def _text(part) -> str:
    """At most ``_TEXT_SCAN_LIMIT`` characters of a part's decoded text."""
    payload = part.get_payload(decode=True) if part is not None else None
    if not isinstance(payload, bytes):
        return ""
    return payload[:_TEXT_SCAN_LIMIT].decode(part.get_content_charset() or "utf-8", errors="replace")


def _status_line(message) -> tuple[str, str]:
    """The status code of an old-style bounce and the text line it appears on (the only text read)."""
    try:
        content = _text(_first_part(message, "text/plain"))
    except LookupError:  # an unknown charset
        content = ""
    for line in content.splitlines():
        code = _status_code(line[:LIMIT])
        if code:
            return code, text.clean(line, 1000)
    return "", ""


def _original_headers(message):
    """The returned original message's headers, from a ``message/rfc822`` or ``text/rfc822-headers`` part."""
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type in ("message/rfc822", "message/global"):
            payload = part.get_payload()
            return payload[0] if isinstance(payload, list) and payload else None
        if content_type == "text/rfc822-headers":
            try:
                return HeaderParser(policy=email.policy.compat32).parsestr(_text(part))
            except (LookupError, ValueError):
                return None
    return None


def _first_part(message, content_type: str):
    return next((part for part in message.walk() if part.get_content_type() == content_type), None)


def _from_report_sender(message) -> bool:
    local = text.address(_raw(message, "From")).partition("@")[0]
    return local in _REPORT_SENDERS or local.startswith("microsoftexchange")


def _raw(message, name: str, limit: int = LIMIT) -> str:
    """A header's raw text, cut to ``limit`` characters, or ""."""
    if message is None:
        return ""
    value = message.get(name)
    return str(value)[:limit] if value is not None else ""


def _decoded(message, name: str) -> str:
    """A header's text with its encoded words decoded (``=?utf-8?q?...?=``), cut to 998 characters first."""
    raw = _raw(message, name)
    try:
        value = str(make_header(decode_header(raw)))
    except (HeaderParseError, LookupError, UnicodeError, ValueError):
        value = raw
    return text.clean(value, LIMIT)


def _strip_type(value) -> str:
    """``rfc822; user@example.com`` → ``user@example.com`` (the address / name / diagnostic type prefix)."""
    return _TYPE_PREFIX_RE.sub("", str(value or ""), count=1)


def _date(value) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(str(value)) if value else None
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
