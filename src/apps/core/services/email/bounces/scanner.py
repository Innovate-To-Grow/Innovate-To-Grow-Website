"""One bounce scan of the Microsoft Graph sending mailbox.

The scan lists the Inbox incrementally (received since the checkpoint less an overlap, oldest first; never the whole
folder), opens only the messages that look like bounce reports, parses them (``dsn``), saves their bounces
(``store``) and moves the checkpoint past what it fully processed. Every request is a GET through the site's Graph
reader, paced on the ``graph_read`` delivery channel together with the mailbox's sends: a throttle or cooldown ends
the scan early with its progress kept, and the next scheduled scan continues from there. Nothing in the mailbox is
changed: no message is marked read, moved or deleted.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db import DataError
from django.utils import timezone

from apps.core.models import EmailBounce

from ..graph.mailbox import GraphMessageNotFound, GraphReadBusy, GraphReadError
from ..telemetry import text
from . import state
from .dsn import BounceReport, parse_report
from .source import active_reader, is_candidate, monitoring, received_at
from .store import save_report

logger = logging.getLogger(__name__)
STAT_KEYS = (
    "listed",
    "candidates",
    "already_processed",
    "opened",
    "not_reports",
    "unstorable",
    "bounces",
    "matched",
    "duplicates",
)


@dataclass
class ScanOutcome:
    status: str  # ok, partial, busy, failed, inactive, paused, locked or disabled
    mailbox: str = ""
    stats: dict = field(default_factory=dict)
    error: str = ""
    retry_after: int | None = None


@dataclass
class _Progress:
    checkpoint: datetime | None
    deadline: float = float("inf")
    stats: dict = field(default_factory=lambda: dict.fromkeys(STAT_KEYS, 0))

    def count(self, key: str, amount: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + amount

    def advance(self, received: datetime) -> None:
        if self.checkpoint is None or received > self.checkpoint:
            self.checkpoint = received


def scan_mailbox(*, now: datetime | None = None) -> ScanOutcome:
    if not monitoring()["bounce_processing_enabled"]:
        return ScanOutcome("disabled")
    reader, mailbox, problem = active_reader()
    if reader is None:
        if mailbox:
            state.record_problem(mailbox, problem)
        return ScanOutcome("inactive", mailbox, error=problem)
    now = now or timezone.now()
    current = state.state_for(mailbox)
    if current.paused:
        return ScanOutcome("paused", mailbox)
    token = state.acquire_lease(mailbox, now)
    if token is None:
        return ScanOutcome("locked", mailbox)
    # Read the checkpoint only now that the lease is held: a "Rescan since" saved before is seen, none lands meanwhile.
    current.refresh_from_db(fields=["checkpoint_at", "initial_lookback_hours"])
    progress = _Progress(current.checkpoint_at, deadline=time.monotonic() + monitoring()["bounce_scan_max_seconds"])
    try:
        status = _scan(reader, mailbox, _start(current, now), now, progress)
    except GraphReadBusy as exc:
        state.finish(mailbox, token, checkpoint=progress.checkpoint, stats=progress.stats, retry_after=exc.retry_after)
        return ScanOutcome("busy", mailbox, progress.stats, retry_after=exc.retry_after)
    except GraphReadError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a scan failure is recorded for the dashboard, never raised.
        logger.error("Email bounce scan failed with an unexpected %s", type(exc).__name__)
        error = f"Unexpected {type(exc).__name__}"
    else:
        state.finish(mailbox, token, checkpoint=progress.checkpoint, stats=progress.stats)
        return ScanOutcome(status, mailbox, progress.stats)
    state.finish(mailbox, token, checkpoint=progress.checkpoint, stats=progress.stats, error=error)
    return ScanOutcome("failed", mailbox, progress.stats, error=error)


def _start(current, now: datetime) -> datetime:
    """Where a scan starts listing: its checkpoint less the overlap, or (first scan) the mailbox's lookback."""
    if current.checkpoint_at is None:
        return now - timedelta(hours=state.lookback_hours(current))
    return current.checkpoint_at - timedelta(seconds=monitoring()["bounce_scan_overlap_seconds"])


def _scan(reader, mailbox: str, since: datetime, now: datetime, progress: _Progress) -> str:
    config = monitoring()
    page_size = int(config["bounce_scan_page_size"])
    for _page in range(int(config["bounce_scan_max_pages"])):
        if time.monotonic() >= progress.deadline:
            return "partial"
        messages = reader.list_received_since("INBOX", since, page_size)
        progress.count("listed", len(messages))
        if not _scan_page(reader, mailbox, messages, progress):
            return "partial"
        if len(messages) < page_size:
            # Caught up: everything received before this scan started has been listed.
            progress.advance(now)
            return "ok"
        last = received_at(messages[-1]) or since
        since = last if last > since else since + timedelta(seconds=1)
    return "partial"


def _scan_page(reader, mailbox: str, messages: list[dict], progress: _Progress) -> bool:
    """Process one page, oldest first, moving the checkpoint past each message; False when the scan's message or time
    budget ran out (the rest waits for the next scan)."""
    budget = int(monitoring()["bounce_scan_max_messages"])
    for message in messages:
        received = received_at(message)
        if received is None:
            continue
        if is_candidate(message):
            if progress.stats["opened"] >= budget or time.monotonic() >= progress.deadline:
                return False
            _process(reader, mailbox, message, received, progress)
        progress.advance(received)
    return True


def _process(reader, mailbox: str, message: dict, received: datetime, progress: _Progress) -> None:
    graph_id = message["id"]
    progress.count("candidates")
    if EmailBounce.objects.filter(mailbox=mailbox, ndr_graph_id=graph_id).exists():
        progress.count("already_processed")
        return
    try:
        raw, _truncated = reader.fetch_mime_head(graph_id, int(monitoring()["bounce_message_max_bytes"]))
    except GraphMessageNotFound:
        return  # deleted or moved since it was listed
    progress.count("opened")
    config = monitoring()
    try:
        report = parse_report(
            raw,
            subject_hint=str(message.get("subject") or ""),
            max_recipients=int(config["bounce_max_recipients_per_report"]),
        )
    except Exception as exc:  # noqa: BLE001 - one malformed report must not stop the scan: it is kept as unknown.
        logger.warning("A bounce report could not be parsed (%s)", type(exc).__name__)
        report = BounceReport((), report_message_id=text.message_id(message.get("internetMessageId")))
    if report is None:
        progress.count("not_reports")
        return
    try:
        result = save_report(mailbox=mailbox, graph_id=graph_id, received_at=received, report=report)
    except (DataError, ValueError, UnicodeError) as exc:
        # Data the database refuses must not block every later scan at this report; an outage still fails the scan.
        logger.warning("A bounce report could not be stored (%s)", type(exc).__name__)
        progress.count("unstorable")
        return
    progress.count("bounces", len(result.created))
    progress.count("matched", result.matched)
    progress.count("duplicates", result.duplicates)
