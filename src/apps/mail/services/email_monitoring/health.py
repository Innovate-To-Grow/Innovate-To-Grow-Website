"""Health of the monitoring itself: whether telemetry is on, when it began, and the bounce processor's state.

Nothing here contacts Microsoft: the bounce processor's readiness is the same local check its scans start with
(configuration, mailbox allow-list, mailbox scope), and its last outcome is what its state row recorded.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.models import BackgroundJob, EmailMonitorState
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND, active_reader

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
    }


def monitoring_health() -> dict:
    return {
        "telemetry_enabled": bool(settings.EMAIL_MONITORING["telemetry_enabled"]),
        "store_subjects": bool(settings.EMAIL_MONITORING["store_subjects"]),
        "retention_days": settings.EMAIL_MONITORING["retention_days"],
        "bounce_retention_days": settings.EMAIL_MONITORING["bounce_retention_days"],
        "monitoring_began": monitoring_began(),
        "bounces": bounce_processing(),
    }
