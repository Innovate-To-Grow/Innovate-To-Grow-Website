"""What the intake card (Helpdesk → Settings) shows, and how the Email Monitoring card describes the intake.

Nothing here contacts Microsoft: whether the intake can read the mailbox is the same local check its scans start with
(configuration, mailbox allow-list, mailbox scope), and its last outcome is what its state row recorded. The cadence
comes from the functions that schedule the scans, so the cards always say how often the Inbox is really read.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.models import BackgroundJob, InboundMessage
from apps.core.services.email.bounces import active_reader
from apps.core.services.email.inbound import InboxReader, format_interval

from ...models import HelpdeskSettings, IntakeState
from . import jobs
from . import state as intake_state

# A scan older than this many intervals means the scans have stopped (most likely the background worker is down).
STALE_INTERVALS = 3
_QUEUED = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)


def cadence() -> dict:
    """``every`` (the interval) and ``catch_up`` (empty when catching up is no sooner), as the card prints them."""
    interval, catch_up = jobs.interval_seconds(), jobs.catch_up_seconds()
    return {"every": format_interval(interval), "catch_up": format_interval(catch_up) if catch_up < interval else ""}


def _level(row: IntakeState | None, *, enabled: bool, active: bool, now) -> str:
    if not enabled:
        return "off"
    if not active:
        return "inactive"
    if row is not None and row.paused:
        return "paused"
    if row is None or row.last_run_finished_at is None:
        return "waiting"
    if row.consecutive_failures:
        return "error"
    stale_after = timedelta(seconds=STALE_INTERVALS * jobs.interval_seconds())
    if row.last_success_at is None or now - row.last_success_at > stale_after:
        return "warning"
    return "ok"


def card(*, now=None) -> dict:
    now = now or timezone.now()
    enabled = bool(HelpdeskSettings.load().enabled)
    reader, mailbox, problem = active_reader()
    row = IntakeState.objects.filter(mailbox=mailbox).first() if mailbox else None
    next_scan = (
        BackgroundJob.objects.filter(kind=jobs.INTAKE_JOB_KIND, status__in=_QUEUED)
        .order_by("available_at")
        .values_list("available_at", flat=True)
        .first()
    )
    waiting = InboundMessage.objects.filter(mailbox=mailbox, status=InboundMessage.Status.PENDING) if mailbox else None
    return {
        "enabled": enabled,
        "active": reader is not None,
        "mailbox": mailbox,
        "problem": problem,
        "state": row,
        "stats": (row.last_run_stats if row else {}) or {},
        "next_scan_at": next_scan,
        "level": _level(row, enabled=enabled, active=reader is not None, now=now),
        **cadence(),
        "scan_running": bool(row and row.lease_until and row.lease_until >= now),
        "waiting": waiting.count() if waiting is not None else 0,
        "url": reverse("admin:helpdesk_intake"),
        "backfill": backfill(row, now),
    }


def backfill(row: IntakeState | None, now) -> dict:
    """The bounds and current values behind the card's "Rescan since" and first-scan lookback forms."""
    low, high = intake_state.lookback_bounds()
    earliest = intake_state.earliest_rescan(now)
    return {
        "max_days": intake_state.max_lookback_days(),
        "timezone": timezone.get_current_timezone_name(),
        # ``datetime-local`` bounds, in the site's time zone: the earliest whole minute allowed, and now.
        "earliest_input": _local_input(earliest + timedelta(seconds=59)),
        "latest_input": _local_input(now),
        "lookback_hours": intake_state.lookback_hours(row),
        "lookback_custom": bool(row and row.initial_lookback_hours is not None),
        "lookback_default": intake_state.default_lookback_hours(),
        "lookback_min": low,
        "lookback_max": high,
    }


def _local_input(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def describe() -> InboxReader:
    """The intake as the Email Monitoring card lists it (``core``'s inbox-reader registry calls this by name)."""
    reader, mailbox, _problem = active_reader()
    if not HelpdeskSettings.load().enabled:
        current = "off"
    elif reader is None:
        current = "inactive"
    elif intake_state.is_paused(mailbox):
        current = "paused"
    else:
        current = "running"
    url = f"{reverse('admin:helpdesk_helpdesksettings_changelist')}#helpdesk-intake"
    return InboxReader("Helpdesk intake", current, jobs.interval_seconds(), url)
