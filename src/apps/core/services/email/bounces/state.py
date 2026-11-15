"""The bounce processor's durable state per mailbox (``EmailMonitorState``): checkpoint, lease, health, and the staff
controls "Rescan since" and first-scan lookback (both bounded by ``bounce_max_lookback_days``, both audited).

A scan takes the mailbox's lease first (a conditional update, never a lock held across Microsoft requests, which the
delivery-rate limiter would refuse), so two workers or a manual "Scan now" never scan one mailbox at once; an
expired lease (a worker stopped mid-scan) is simply taken over. A scan reads the checkpoint only once it holds the
lease, and a rescan moves it only while no live lease is held (under a short row lock), so a running scan never saves
its checkpoint over a rescan. Every other write is a single statement.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import EmailMonitorState

from ..telemetry import text

logger = logging.getLogger(__name__)


def state_for(mailbox: str) -> EmailMonitorState:
    try:
        with transaction.atomic():
            return EmailMonitorState.objects.get_or_create(mailbox=mailbox)[0]
    except IntegrityError:  # created by another process meanwhile
        return EmailMonitorState.objects.get(mailbox=mailbox)


def acquire_lease(mailbox: str, now: datetime) -> uuid.UUID | None:
    token = uuid.uuid4()
    lease_until = now + timedelta(seconds=settings.EMAIL_MONITORING["bounce_lease_seconds"])
    free = Q(lease_until__isnull=True) | Q(lease_until__lt=now)
    taken = EmailMonitorState.objects.filter(free, mailbox=mailbox, paused=False).update(
        lease_token=token, lease_until=lease_until, last_run_started_at=now, updated_at=now
    )
    return token if taken else None


def _held(mailbox: str, token: uuid.UUID):
    return EmailMonitorState.objects.filter(mailbox=mailbox, lease_token=token)


def finish(mailbox: str, token: uuid.UUID, *, checkpoint, stats: dict, error: str = "", retry_after=None) -> None:
    """Save the run's progress and outcome and give the lease back. ``error`` marks a failed run (shown on the
    dashboard); ``retry_after`` (seconds) is when Microsoft asked to be contacted again."""
    now = timezone.now()
    values = {
        "lease_token": None,
        "lease_until": None,
        "last_run_finished_at": now,
        "last_run_stats": stats,
        "next_run_after": now + timedelta(seconds=retry_after) if retry_after else None,
        "updated_at": now,
    }
    if checkpoint is not None:
        values["checkpoint_at"] = checkpoint
    if error:
        values.update(
            last_error=text.scrub(error), last_error_at=now, consecutive_failures=F("consecutive_failures") + 1
        )
    elif retry_after is None:
        # A scan held back by Microsoft's pacing (``retry_after``) neither succeeded nor failed.
        values.update(last_success_at=now, consecutive_failures=0)
    _held(mailbox, token).update(**values)


def record_problem(mailbox: str, problem: str) -> None:
    """Bounce processing cannot run for ``mailbox`` (out of scope, not allowed): shown like a failed run."""
    now = timezone.now()
    state_for(mailbox)
    EmailMonitorState.objects.filter(mailbox=mailbox).update(
        last_error=text.scrub(problem), last_error_at=now, last_run_finished_at=now, updated_at=now
    )


def set_paused(mailbox: str, paused: bool) -> None:
    state_for(mailbox)
    EmailMonitorState.objects.filter(mailbox=mailbox).update(paused=paused, updated_at=timezone.now())


def is_paused(mailbox: str) -> bool:
    return EmailMonitorState.objects.filter(mailbox=mailbox, paused=True).exists()


def max_lookback_days() -> int:
    """How far back a scan can be sent: ``bounce_max_lookback_days``, never past ``bounce_retention_days``."""
    config = settings.EMAIL_MONITORING
    return max(1, min(int(config["bounce_max_lookback_days"]), int(config["bounce_retention_days"])))


def lookback_bounds() -> tuple[int, int]:
    """The allowed first-scan lookback, in hours: one hour to the longest lookback."""
    return 1, max_lookback_days() * 24


def _bounded(hours) -> int:
    low, high = lookback_bounds()
    return min(max(int(hours), low), high)


def default_lookback_hours() -> int:
    return _bounded(settings.EMAIL_MONITORING["bounce_initial_lookback_hours"])


def lookback_hours(current: EmailMonitorState | None) -> int:
    """The first scan's lookback: what staff set, else the default; kept within the bounds whatever the row holds."""
    hours = getattr(current, "initial_lookback_hours", None)
    return default_lookback_hours() if hours is None else _bounded(hours)


def set_lookback(mailbox: str, hours: int | None, *, actor=None) -> int | None:
    """Set the first-scan lookback of ``mailbox`` (``None``: back to the default); returns the previous value."""
    low, high = lookback_bounds()
    if hours is not None and not low <= hours <= high:
        raise ValueError(f"The first-scan lookback must be from {low} to {high} hours.")
    current = state_for(mailbox)
    previous = current.initial_lookback_hours
    if previous != hours:
        EmailMonitorState.objects.filter(pk=current.pk).update(initial_lookback_hours=hours, updated_at=timezone.now())
        _record(actor, current, "lookback", f"First-scan lookback: {_hours(previous)} → {_hours(hours)}.")
    return previous


@dataclass(frozen=True)
class Rescan:
    """``moved``, or why nothing changed: ``future``, ``too_early``, ``not_earlier`` or ``running``."""

    status: str
    since: datetime
    earliest: datetime
    previous: datetime | None = None
    paused: bool = False
    lease_until: datetime | None = None


def earliest_rescan(now: datetime) -> datetime:
    return now - timedelta(days=max_lookback_days())


def rescan_since(mailbox: str, since: datetime, *, actor=None, now: datetime | None = None) -> Rescan:
    """Move the checkpoint back to ``since``: the next scan reads the Inbox again from there (less the overlap), and
    skips the reports already recorded. Refused for a future time, one past the longest lookback, one not before the
    checkpoint (moving it forward would skip mail), and while a scan holds the lease. It starts no scan and leaves a
    paused mailbox paused; an expired lease is released, so the scan that held it saves nothing."""
    now = now or timezone.now()
    earliest = earliest_rescan(now)
    if since > now:
        return Rescan("future", since, earliest)
    if since < earliest:
        return Rescan("too_early", since, earliest)
    pk = state_for(mailbox).pk
    with transaction.atomic():
        row = EmailMonitorState.objects.select_for_update().get(pk=pk)
        found = {"previous": row.checkpoint_at, "paused": row.paused}
        if row.lease_until is not None and row.lease_until >= now:
            return Rescan("running", since, earliest, lease_until=row.lease_until, **found)
        if row.checkpoint_at is not None and row.checkpoint_at <= since:
            return Rescan("not_earlier", since, earliest, **found)
        EmailMonitorState.objects.filter(pk=pk).update(
            checkpoint_at=since, lease_token=None, lease_until=None, updated_at=now
        )
        message = f"Rescan since {_when(since)}: checkpoint moved back from {_when(row.checkpoint_at)}."
        _record(actor, row, "rescan", message)
    return Rescan("moved", since, earliest, **found)


def _hours(hours: int | None) -> str:
    return f"default ({default_lookback_hours()} h)" if hours is None else f"{hours} h"


def _when(value: datetime | None) -> str:
    return f"{timezone.localtime(value):%Y-%m-%d %H:%M %Z}" if value is not None else "none (no scan yet)"


def _record(actor, row: EmailMonitorState, action: str, message: str) -> None:
    """Admin history (LogEntry) plus one log line; both carry only the site's own mailbox and times."""
    actor_id = getattr(actor, "pk", None)
    logger.info("email_bounce_state action=%s mailbox=%s actor=%s: %s", action, row.mailbox, actor_id or "-", message)
    if actor_id:
        LogEntry.objects.log_actions(
            user_id=actor_id, queryset=[row], action_flag=CHANGE, change_message=message, single_object=True
        )
