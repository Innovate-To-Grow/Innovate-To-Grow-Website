"""Matching Message Trace rows (one per message and recipient) to the outgoing emails they report on, without guessing.

1. Exact: the trace's ``messageId`` is the email's Message-ID (the MIME form of sendMail), compared exactly.
2. Inferred: the email has no Message-ID (the JSON form), and exactly one traced message to the same recipient, with
   the same subject, received from two minutes before to ten minutes after the email was accepted, qualifies, and
   that message qualifies for no other such email. A traced Message-ID the site knows is never inferred onto another
   email. Only a fully read window is used for this (``complete``): a partly read one could hide a second candidate.

An email's status is the worst of its recipients' (``DELIVERY_STATUS_RANK``). While any recipient is pending (or not
in the trace yet), nothing changes.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import OutboundEmail
from apps.core.models.records.email_telemetry import DELIVERY_STATUS_RANK

from ...telemetry import text

DeliveryStatus = OutboundEmail.DeliveryStatus
# Message Trace statuses with a meaning here; any other (pending, gettingStatus, a future value) changes nothing.
TRACE_STATUS = {
    "delivered": DeliveryStatus.DELIVERED,
    "expanded": DeliveryStatus.DELIVERED,
    "failed": DeliveryStatus.FAILURE_CONFIRMED,
    "quarantined": DeliveryStatus.QUARANTINED,
    "filteredAsSpam": DeliveryStatus.FILTERED_AS_SPAM,
}
TRACE_STATUS_LENGTH = 16
EARLIEST = timedelta(minutes=2)  # before acceptance: the site's and Exchange's clocks differ
LATEST = timedelta(minutes=10)  # after acceptance
_LOOKUP_BATCH = 500


@dataclass(frozen=True)
class TraceRow:
    message_id: str
    recipient: str
    status: str
    received: datetime | None
    subject_digest: str


@dataclass(frozen=True)
class Verdict:
    """``delivery_status`` None: leave it as it is (pending); ``trace_status`` is the raw status kept either way."""

    delivery_status: str | None
    trace_status: str


def _received(value) -> datetime | None:
    parsed = parse_datetime(str(value or "")[:64])
    if parsed is None:
        return None
    return parsed if timezone.is_aware(parsed) else parsed.replace(tzinfo=UTC)


def parse_rows(rows) -> list[TraceRow]:
    return [
        TraceRow(
            message_id=text.message_id(row.get("messageId")),
            recipient=text.address(row.get("recipientAddress")),
            status=text.clean(row.get("status"), TRACE_STATUS_LENGTH),
            received=_received(row.get("receivedDateTime")),
            subject_digest=text.subject_digest(text.clean(row.get("subject"), 998)),
        )
        for row in rows
    ]


def verdict(email: OutboundEmail, rows: list[TraceRow]) -> Verdict | None:
    """The worst status of the email's recipients, or None when the rows do not cover every recipient yet."""
    envelope = set(text.addresses([email.recipient, *(email.recipients or [])]))
    seen = {row.recipient for row in rows if row.recipient}
    # Exchange may report a recipient by its primary address rather than the alias the site sent to, so as many
    # traced recipients as envelope ones also covers the email.
    if not rows or not (envelope <= seen or len(seen) >= max(len(envelope), 1)):
        return None
    pending = next((row for row in rows if row.status not in TRACE_STATUS), None)
    if pending is not None:
        return Verdict(None, pending.status)
    worst = max(rows, key=lambda row: DELIVERY_STATUS_RANK[TRACE_STATUS[row.status]])
    return Verdict(TRACE_STATUS[worst.status], worst.status)


def _known_message_ids(message_ids: list[str]) -> set[str]:
    known = set()
    for start in range(0, len(message_ids), _LOOKUP_BATCH):
        batch = message_ids[start : start + _LOOKUP_BATCH]
        known.update(
            OutboundEmail.objects.filter(internet_message_id__in=batch).values_list("internet_message_id", flat=True)
        )
    return known


def sent_at(email: OutboundEmail) -> datetime | None:
    """When the email left: its acceptance, or for an uncertain send its last attempt."""
    return email.accepted_at or email.last_attempt_at


def _inferred(emails, groups: dict[str, list[TraceRow]]) -> dict:
    """Pair JSON-sent emails with messages no known Message-ID claims, one to one; ``{email pk: (email, rows)}``."""
    by_key = defaultdict(list)
    for email in emails:
        if not email.internet_message_id and email.subject_digest and sent_at(email) is not None:
            by_key[(email.recipient, email.subject_digest)].append(email)
    options = defaultdict(list)  # email pk -> message ids that qualify for it
    chosen = {}
    for message_id, rows in groups.items():
        times = [row.received for row in rows if row.received is not None]
        digest = rows[0].subject_digest
        if not times or not digest or any(row.subject_digest != digest for row in rows):
            continue
        received = min(times)
        fits = {
            email.pk: email
            for recipient in {row.recipient for row in rows if row.recipient}
            for email in by_key.get((recipient, digest), ())
            if sent_at(email) - EARLIEST <= received <= sent_at(email) + LATEST
        }
        for pk in fits:
            options[pk].append(message_id)
        if len(fits) == 1:
            chosen[message_id] = next(iter(fits.values()))
    return {
        email.pk: (email, groups[message_id])
        for message_id, email in chosen.items()
        if options[email.pk] == [message_id]
    }


def match_rows(emails: list[OutboundEmail], rows: list[TraceRow], *, complete: bool) -> dict:
    """``{email pk: (email, Verdict)}`` for the emails the rows report on (pending ones included). *emails* must be
    every email the site sent in the rows' window, whatever its status, so an inference sees all its rivals."""
    groups = defaultdict(list)
    for row in rows:
        if row.message_id:
            groups[row.message_id].append(row)
    matched = {
        email.pk: (email, groups[email.internet_message_id]) for email in emails if email.internet_message_id in groups
    }
    if complete:
        known = _known_message_ids(sorted(groups))
        matched.update(_inferred(emails, {key: value for key, value in groups.items() if key not in known}))
    found = {}
    for pk, (email, email_rows) in matched.items():
        result = verdict(email, email_rows)
        if result is not None:
            found[pk] = (email, result)
    return found
