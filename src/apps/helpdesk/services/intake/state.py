"""The intake's durable state per mailbox (``IntakeState``): checkpoint, lease, health, and the controls on the intake
card: pause, "Rescan since" and the first-scan lookback (both bounded by ``inbox_max_lookback_days``), each audited.

It is separate from bounce processing's state (``core.EmailMonitorState``): both scans read the same Inbox, each from
its own checkpoint, so pausing or rescanning one never moves the other. The lease rule is the bounce processor's. A
scan takes the mailbox's lease first (a conditional update, never a lock held across Microsoft requests, which the
delivery-rate limiter would refuse), so two workers or a "Scan now" never scan one mailbox at once; an expired lease
(a worker stopped mid-scan) is taken over. A scan reads the checkpoint only once it holds the lease, and a rescan
moves it only while no live lease is held (under a short row lock), so a running scan never saves its checkpoint over
a rescan. Every other write is a single statement.
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

from apps.core.services.email.telemetry import text

from ...models import IntakeState

logger = logging.getLogger(__name__)


def _config() -> dict:
    return settings.EMAIL_MONITORING


def state_for(mailbox: str) -> IntakeState:
    try:
        with transaction.atomic():
            return IntakeState.objects.get_or_create(mailbox=mailbox)[0]
    except IntegrityError:  # created by another process meanwhile
        return IntakeState.objects.get(mailbox=mailbox)


def is_paused(mailbox: str) -> bool:
    return IntakeState.objects.filter(mailbox=mailbox, paused=True).exists()


def acquire_lease(mailbox: str, now: datetime) -> uuid.UUID | None:
    token = uuid.uuid4()
    lease_until = now + timedelta(seconds=int(_config()["bounce_lease_seconds"]))
    free = Q(lease_until__isnull=True) | Q(lease_until__lt=now)
    taken = IntakeState.objects.filter(free, mailbox=mailbox, paused=False).update(
        lease_token=token, lease_until=lease_until, last_run_started_at=now, updated_at=now
    )
    return token if taken else None


def finish(mailbox: str, token: uuid.UUID, *, checkpoint, stats: dict, error: str = "", retry_after=None) -> None:
    """Save the scan's progress and outcome and give the lease back. ``error`` marks a failed scan (shown on the
    card); ``retry_after`` (seconds) is when Microsoft asked to be contacted again. Nothing is saved by a scan whose
    lease was released meanwhile (an expired lease a rescan cleared)."""
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
    IntakeState.objects.filter(mailbox=mailbox, lease_token=token).update(**values)


def record_problem(mailbox: str, problem: str) -> None:
    """The intake cannot run for ``mailbox`` (out of scope, not allowed): shown like a failed scan."""
    now = timezone.now()
    state_for(mailbox)
    IntakeState.objects.filter(mailbox=mailbox).update(
        last_error=text.scrub(problem), last_error_at=now, last_run_finished_at=now, updated_at=now
    )


def set_paused(mailbox: str, paused: bool, *, actor=None) -> bool:
    """Pause or resume the intake of ``mailbox``; True when that changed something (then audited). A scan already
    running finishes; the next one, and every import, waits until it is resumed."""
    row = state_for(mailbox)
    changed = IntakeState.objects.filter(pk=row.pk, paused=not paused).update(paused=paused, updated_at=timezone.now())
    if changed:
        _record(actor, row, "pause" if paused else "resume", "Intake paused." if paused else "Intake resumed.")
    return bool(changed)


def max_lookback_days() -> int:
    """How far back the intake can be sent: ``inbox_max_lookback_days``, at least one day."""
    return max(1, int(_config()["inbox_max_lookback_days"]))


def lookback_bounds() -> tuple[int, int]:
    """The allowed first-scan lookback, in hours: one hour to the longest lookback."""
    return 1, max_lookback_days() * 24


def _bounded(hours) -> int:
    low, high = lookback_bounds()
    return min(max(int(hours), low), high)


def default_lookback_hours() -> int:
    return _bounded(_config()["inbox_initial_lookback_hours"])


def lookback_hours(current: IntakeState | None) -> int:
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
        IntakeState.objects.filter(pk=current.pk).update(initial_lookback_hours=hours, updated_at=timezone.now())
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
    """Move the intake's checkpoint back to ``since``: its next scan lists the Inbox again from there (less the
    overlap) and records only what is not in the queue yet, so no message is imported twice. Refused for a future
    time, one past the longest lookback, one not before the checkpoint (moving it forward would skip mail), and while
    a scan holds the lease. It starts no scan and leaves a paused intake paused; an expired lease is released, so the
    scan that held it saves nothing. Bounce processing's checkpoint is never touched."""
    now = now or timezone.now()
    earliest = earliest_rescan(now)
    if since > now:
        return Rescan("future", since, earliest)
    if since < earliest:
        return Rescan("too_early", since, earliest)
    pk = state_for(mailbox).pk
    with transaction.atomic():
        row = IntakeState.objects.select_for_update().get(pk=pk)
        found = {"previous": row.checkpoint_at, "paused": row.paused}
        if row.lease_until is not None and row.lease_until >= now:
            return Rescan("running", since, earliest, lease_until=row.lease_until, **found)
        if row.checkpoint_at is not None and row.checkpoint_at <= since:
            return Rescan("not_earlier", since, earliest, **found)
        IntakeState.objects.filter(pk=pk).update(
            checkpoint_at=since, lease_token=None, lease_until=None, updated_at=now
        )
        message = f"Rescan since {_when(since)}: checkpoint moved back from {_when(row.checkpoint_at)}."
        _record(actor, row, "rescan", message)
    return Rescan("moved", since, earliest, **found)


def _hours(hours: int | None) -> str:
    return f"default ({default_lookback_hours()} h)" if hours is None else f"{hours} h"


def _when(value: datetime | None) -> str:
    return f"{timezone.localtime(value):%Y-%m-%d %H:%M %Z}" if value is not None else "none (no scan yet)"


def _record(actor, row: IntakeState, action: str, message: str) -> None:
    """Admin history (LogEntry) plus one log line; both carry only the site's own mailbox and times."""
    actor_id = getattr(actor, "pk", None)
    logger.info(
        "helpdesk_intake_state action=%s mailbox=%s actor=%s: %s", action, row.mailbox, actor_id or "-", message
    )
    if actor_id:
        LogEntry.objects.log_actions(
            user_id=actor_id, queryset=[row], action_flag=CHANGE, change_message=message, single_object=True
        )
