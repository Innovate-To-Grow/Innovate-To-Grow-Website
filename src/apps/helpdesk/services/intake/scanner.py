"""One intake scan: list the Inbox from the helpdesk's own checkpoint and record every message in the inbound queue.

The scan lists the Graph mailbox's Inbox incrementally (received since the checkpoint less an overlap, oldest first;
the first scan reads back the mailbox's first-scan lookback; never the whole folder), records each listed message once
in ``core``'s inbound queue (metadata only, cleaned and scrubbed: a message already recorded is not recorded again),
and moves the checkpoint past what it recorded. It opens no message: the ingest reads each recorded message's MIME
afterwards. It lists with the bounce scan's bounds (``bounce_scan_page_size``, ``bounce_scan_max_pages``,
``bounce_scan_overlap_seconds``, ``bounce_scan_max_seconds``), every request a GET paced on the ``graph_read``
channel: a throttle or cooldown ends the scan with its progress kept, and the next scan continues from there.
Nothing in the mailbox changes. Bounce processing lists the same Inbox for reports on its own schedule and checkpoint.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.services.email import inbound
from apps.core.services.email.bounces import active_reader
from apps.core.services.email.bounces.source import is_candidate, received_at
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError

from ...models import HelpdeskSettings
from . import state

logger = logging.getLogger(__name__)
STAT_KEYS = ("listed", "recorded")


@dataclass
class IntakeOutcome:
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

    def advance(self, received: datetime) -> None:
        if self.checkpoint is None or received > self.checkpoint:
            self.checkpoint = received


def _config() -> dict:
    return settings.EMAIL_MONITORING


def scan_inbox(*, now: datetime | None = None) -> IntakeOutcome:
    if not HelpdeskSettings.load().enabled:
        return IntakeOutcome("disabled")
    reader, mailbox, problem = active_reader()
    if reader is None:
        if mailbox:
            state.record_problem(mailbox, problem)
        return IntakeOutcome("inactive", mailbox, error=problem)
    now = now or timezone.now()
    current = state.state_for(mailbox)
    if current.paused:
        return IntakeOutcome("paused", mailbox)
    token = state.acquire_lease(mailbox, now)
    if token is None:
        return IntakeOutcome("locked", mailbox)
    # Read the checkpoint only now that the lease is held: a "Rescan since" saved before is seen, none lands meanwhile.
    current.refresh_from_db(fields=["checkpoint_at", "initial_lookback_hours"])
    progress = _Progress(current.checkpoint_at, deadline=time.monotonic() + int(_config()["bounce_scan_max_seconds"]))
    try:
        status = _scan(reader, mailbox, _start(current, now), now, progress)
    except GraphReadBusy as exc:
        state.finish(mailbox, token, checkpoint=progress.checkpoint, stats=progress.stats, retry_after=exc.retry_after)
        return IntakeOutcome("busy", mailbox, progress.stats, retry_after=exc.retry_after)
    except GraphReadError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a scan failure is recorded for the card, never raised.
        logger.error("Helpdesk intake scan failed with an unexpected %s", type(exc).__name__)
        error = f"Unexpected {type(exc).__name__}"
    else:
        state.finish(mailbox, token, checkpoint=progress.checkpoint, stats=progress.stats)
        return IntakeOutcome(status, mailbox, progress.stats)
    state.finish(mailbox, token, checkpoint=progress.checkpoint, stats=progress.stats, error=error)
    return IntakeOutcome("failed", mailbox, progress.stats, error=error)


def _start(current, now: datetime) -> datetime:
    """Where a scan starts listing: its checkpoint less the overlap, or (first scan) the mailbox's lookback."""
    if current.checkpoint_at is None:
        return now - timedelta(hours=state.lookback_hours(current))
    return current.checkpoint_at - timedelta(seconds=int(_config()["bounce_scan_overlap_seconds"]))


def _scan(reader, mailbox: str, since: datetime, now: datetime, progress: _Progress) -> str:
    page_size = int(_config()["bounce_scan_page_size"])
    for _page in range(int(_config()["bounce_scan_max_pages"])):
        if time.monotonic() >= progress.deadline:
            return "partial"
        messages = reader.list_received_since("INBOX", since, page_size)
        progress.stats["listed"] += len(messages)
        for message in messages:
            received = received_at(message)
            if received is None:
                continue
            if inbound.record(mailbox, message, received, candidate=is_candidate(message)):
                progress.stats["recorded"] += 1
            progress.advance(received)
        if len(messages) < page_size:
            # Caught up: everything received before this scan started has been listed.
            progress.advance(now)
            return "ok"
        last = received_at(messages[-1]) or since
        since = last if last > since else since + timedelta(seconds=1)
    return "partial"
