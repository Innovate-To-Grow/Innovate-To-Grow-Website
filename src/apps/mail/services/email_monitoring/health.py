"""Health of the monitoring itself: whether telemetry is on, when it began, and the bounce processor's state (with the
bounds of its "Rescan since" and first-scan lookback controls).

Nothing here contacts Microsoft: the bounce processor's readiness is the same local check its scans start with
(configuration, mailbox allow-list, mailbox scope), and its last outcome is what its state row recorded.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.models import BackgroundJob, EmailMonitorState
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND, active_reader
from apps.core.services.email.bounces import state as bounce_state

from .scope import monitoring_began

# A scan older than this many intervals means the scans have stopped (most likely the background worker is down).
STALE_INTERVALS = 3


def _level(state: EmailMonitorState | None, *, active: bool, now) -> str:
    if not settings.EMAIL_MONITORING["bounce_processing_enabled"] or not active:
        return "inactive"
    if state is None or state.last_run_finished_at is None:
        return "waiting"
    if state.paused:
        return "paused"
    if state.consecutive_failures:
        return "error"
    stale_after = timedelta(seconds=STALE_INTERVALS * settings.EMAIL_MONITORING["bounce_scan_interval_seconds"])
    if state.last_success_at is None or now - state.last_success_at > stale_after:
        return "warning"
    return "ok"


def bounce_processing() -> dict:
    now = timezone.now()
    reader, mailbox, problem = active_reader()
    state = EmailMonitorState.objects.filter(mailbox=mailbox).first() if mailbox else None
    next_job = (
        BackgroundJob.objects.filter(
            kind=BOUNCE_SCAN_JOB_KIND, status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY]
        )
        .order_by("available_at")
        .values_list("available_at", flat=True)
        .first()
    )
    return {
        "enabled": bool(settings.EMAIL_MONITORING["bounce_processing_enabled"]),
        "active": reader is not None,
        "mailbox": mailbox,
        "problem": problem,
        "state": state,
        "stats": (state.last_run_stats if state else {}) or {},
        "next_scan_at": next_job,
        "level": _level(state, active=reader is not None, now=now),
        "interval_minutes": max(1, settings.EMAIL_MONITORING["bounce_scan_interval_seconds"] // 60),
        "scan_running": bool(state and state.lease_until and state.lease_until >= now),
        "backfill": backfill(state, now),
    }


def backfill(state: EmailMonitorState | None, now) -> dict:
    """The bounds and current values behind the card's "Rescan since" and first-scan lookback forms."""
    low, high = bounce_state.lookback_bounds()
    earliest = bounce_state.earliest_rescan(now)
    return {
        "max_days": bounce_state.max_lookback_days(),
        "timezone": timezone.get_current_timezone_name(),
        # ``datetime-local`` bounds, in the site's time zone: the earliest whole minute allowed, and now.
        "earliest_input": _local_input(earliest + timedelta(seconds=59)),
        "latest_input": _local_input(now),
        "lookback_hours": bounce_state.lookback_hours(state),
        "lookback_custom": bool(state and state.initial_lookback_hours is not None),
        "lookback_default": bounce_state.default_lookback_hours(),
        "lookback_min": low,
        "lookback_max": high,
    }


def _local_input(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def monitoring_health() -> dict:
    return {
        "telemetry_enabled": bool(settings.EMAIL_MONITORING["telemetry_enabled"]),
        "store_subjects": bool(settings.EMAIL_MONITORING["store_subjects"]),
        "retention_days": settings.EMAIL_MONITORING["retention_days"],
        "bounce_retention_days": settings.EMAIL_MONITORING["bounce_retention_days"],
        "monitoring_began": monitoring_began(),
        "bounces": bounce_processing(),
    }
