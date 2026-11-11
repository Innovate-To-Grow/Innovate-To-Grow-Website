"""One run of the ingest: drain ``core``'s inbound queue into tickets, within a message and a time budget.

For each due row, oldest first: skip it as a duplicate when a ticket already holds its Message-ID, else read its raw
MIME through the site's Graph reader (GET only, paced on the ``graph_read`` delivery channel; nothing in the mailbox
changes), parse it, classify it, store it, and settle the row with what became of it. A message that is gone from
the mailbox is skipped with the reason; a read or processing failure retries with backoff and, after the last
attempt, is listed under Helpdesk → Ingest problems; a throttle from Microsoft ends the run and the row waits for
the time Microsoft asked for (without spending an attempt). Nothing is ever sent.
"""

import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings as django_settings
from django.utils import timezone

from apps.core.models import InboundMessage
from apps.core.services.email.bounces import active_reader
from apps.core.services.email.graph.mailbox import GraphMessageNotFound, GraphReadBusy, GraphReadError
from apps.core.services.email.inbound import consume

from ...models import HelpdeskSettings, TicketMessage
from .classify import classify_message, own_addresses
from .parse import parse
from .store import store

logger = logging.getLogger(__name__)
GONE = "No longer in the mailbox: deleted or moved in Outlook before it was imported."
OTHER_MAILBOX = "Received by a mailbox the site no longer reads."


@dataclass
class RunOutcome:
    stopped: str = "empty"  # empty, budget, time, busy, no_reader or disabled
    processed: int = 0
    tickets: int = 0
    failed: int = 0
    busy_until: datetime | None = None
    problem: str = ""


def stale_after(settings: HelpdeskSettings) -> timedelta:
    """A row ``processing`` longer than this was left by a stopped worker (a run never takes nearly as long)."""
    return timedelta(seconds=max(900, 5 * int(settings.ingest_max_seconds)))


def run(settings: HelpdeskSettings | None = None) -> RunOutcome:
    settings = settings or HelpdeskSettings.load()
    if not settings.enabled:
        return RunOutcome("disabled")
    consume.recover_stale(stale_after=stale_after(settings), max_attempts=int(settings.max_attempts))
    reader, mailbox, problem = active_reader()
    if reader is None:
        return RunOutcome("no_reader", problem=problem)
    outcome = RunOutcome()
    deadline = time.monotonic() + int(settings.ingest_max_seconds)
    own = own_addresses(mailbox)
    while True:
        if outcome.processed >= int(settings.ingest_batch_size):
            outcome.stopped = "budget"
            break
        if time.monotonic() >= deadline:
            outcome.stopped = "time"
            break
        row = consume.claim_next()
        if row is None:
            break
        try:
            _process(row, reader, settings, own, outcome)
        except GraphReadBusy as exc:
            outcome.busy_until = timezone.now() + timedelta(seconds=max(1, int(exc.retry_after)))
            consume.defer(row, outcome.busy_until)
            outcome.stopped = "busy"
            break
        outcome.processed += 1
    return outcome


def _origin(exc: BaseException) -> str:
    """``module:line`` of the innermost frame ``exc`` was raised from (no message text, for the log line)."""
    origin = "?"
    for frame, line in traceback.walk_tb(exc.__traceback__):
        origin = f"{frame.f_globals.get('__name__', '?')}:{line}"
    return origin


def _read_limit(settings: HelpdeskSettings) -> int:
    return max(1, min(int(settings.message_max_bytes), int(django_settings.GRAPH_INBOX_MESSAGE_MAX_BYTES)))


def _duplicate_ticket(row: InboundMessage) -> int | None:
    if not row.internet_message_id:
        return None
    message = (
        TicketMessage.objects.filter(internet_message_id=row.internet_message_id, kind__in=TicketMessage.INBOUND_KINDS)
        .select_related("ticket")
        .first()
    )
    return message.ticket.number if message is not None else None


def _process(row: InboundMessage, reader, settings: HelpdeskSettings, own: frozenset, outcome: RunOutcome) -> None:
    if row.mailbox != reader.mailbox:
        consume.skip(row, OTHER_MAILBOX)
        return
    duplicate_of = _duplicate_ticket(row)
    if duplicate_of is not None:
        consume.done(row, result={"ticket": duplicate_of, "duplicate": True})
        return
    try:
        raw, truncated = reader.fetch_mime_head(row.graph_id, _read_limit(settings))
    except GraphMessageNotFound:
        consume.skip(row, GONE)
        return
    except GraphReadBusy:
        raise
    except GraphReadError as exc:
        outcome.failed += int(consume.retry(row, str(exc), max_attempts=int(settings.max_attempts)))
        return
    try:
        parsed = parse(raw, truncated=truncated)
        classified = classify_message(parsed, mailbox=reader.mailbox, settings=settings)
        stored = store(row, parsed, classified, settings, own=own)
    except Exception as exc:  # noqa: BLE001 - one bad message must not stop the queue: it is retried, then listed.
        # The type and where it was raised, never the exception's text or traceback: those can quote the message (a
        # database error's detail, a parser's complaint), and the logs would keep it unscrubbed and past retention.
        logger.error("Helpdesk could not import an inbound message (%s at %s)", type(exc).__name__, _origin(exc))
        error = f"Could not be imported ({type(exc).__name__})."
        outcome.failed += int(consume.retry(row, error, max_attempts=int(settings.max_attempts)))
        return
    result = {"ticket": stored.ticket.number, "created": stored.created, "rule": stored.rule}
    if stored.duplicate:
        result["duplicate"] = True
    verdict = classified.verdict
    consume.done(row, classification=verdict.classification, subtype=verdict.subtype, result=result)
    outcome.tickets += int(stored.created)
