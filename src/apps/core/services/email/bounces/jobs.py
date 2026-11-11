"""The bounce processor in the durable background worker: one outbox job per scan, each queueing the next.

``ensure_scheduled`` (run by the worker's maintenance: at start-up, then hourly) queues a scan when none is waiting,
which restarts the chain if it ever breaks; the dashboard's "Scan now" queues one at once (``run_now``). A scan job
has one attempt and never raises for Microsoft's answers: the next scheduled scan is its retry, after the interval
or Microsoft's longer Retry-After. Overlapping jobs are harmless: the mailbox lease lets only one scan run. A scan
that recorded new inbound messages queues the job of every inbound-mail consumer (``inbound.notify_consumers``).
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.models import BackgroundJob

from ..inbound import active_consumer_kinds, notify_consumers

BOUNCE_SCAN_JOB_KIND = "core.email_bounce_scan"
# A scan that stopped at its message budget continues sooner than the regular interval.
_CATCH_UP_SECONDS = 120
_WAITING = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)
_FINISHED = (BackgroundJob.Status.SUCCEEDED, BackgroundJob.Status.FAILED, BackgroundJob.Status.CANCELLED)
FINISHED_JOB_RETENTION = timedelta(days=7)


def register_bounce_jobs() -> None:
    """Called from ``CoreConfig.ready``."""
    from apps.core.services.background_jobs import register_job_kind

    register_job_kind(BOUNCE_SCAN_JOB_KIND, handler="apps.core.services.email.bounces.jobs.run_scan_job")


def _interval() -> int:
    """The bounce interval, or the shorter inbox interval while an inbound-mail consumer (the helpdesk) is on."""
    config = settings.EMAIL_MONITORING
    seconds = int(config["bounce_scan_interval_seconds"])
    if active_consumer_kinds():
        seconds = min(seconds, int(config["inbox_scan_interval_seconds"]))
    return max(60, seconds)


def enabled() -> bool:
    return bool(settings.EMAIL_MONITORING["bounce_processing_enabled"])


def _enqueue(available_at: datetime, label: str) -> bool:
    """Queue one scan. Callers first check that none is waiting; two workers racing past that check queue two, and
    the chain still continues as one: a scan that finds another waiting queues no successor."""
    from apps.core.services.background_jobs import enqueue_job

    _job, created = enqueue_job(
        kind=BOUNCE_SCAN_JOB_KIND,
        dedupe_key=f"{label}:{available_at.isoformat()}",
        payload={"requested": label},
        max_attempts=1,
        available_at=available_at,
    )
    return created


def ensure_scheduled(*, now: datetime | None = None) -> bool:
    """Queue a scan now unless one is waiting or running; True when one was queued."""
    if not enabled():
        return False
    waiting = (*_WAITING, BackgroundJob.Status.PROCESSING)
    if BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND, status__in=waiting).exists():
        return False
    return _enqueue(now or timezone.now(), "scheduled")


def run_now(*, now: datetime | None = None) -> bool:
    """Queue a scan to run at once (the dashboard's "Scan now")."""
    if not enabled():
        return False
    return _enqueue(now or timezone.now(), "manual")


def next_delay(outcome) -> int:
    """Seconds until the scan after ``outcome``: the interval, sooner to catch up, later when Microsoft asked."""
    interval = _interval()
    if outcome is None:
        return interval
    if outcome.retry_after:
        return max(interval, int(outcome.retry_after))
    return min(interval, _CATCH_UP_SECONDS) if outcome.status == "partial" else interval


def run_scan_job(job) -> None:
    from .scanner import scan_mailbox

    outcome = None
    try:
        outcome = scan_mailbox()
        if outcome.stats.get("recorded"):
            notify_consumers()
    finally:
        if enabled() and not BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND, status__in=_WAITING).exists():
            _enqueue(timezone.now() + timedelta(seconds=next_delay(outcome)), "scheduled")


def purge_finished_jobs(*, now: datetime | None = None) -> int:
    """Delete finished scan jobs older than a week (one is queued every interval)."""
    cutoff = (now or timezone.now()) - FINISHED_JOB_RETENTION
    deleted, _ = BackgroundJob.objects.filter(
        kind=BOUNCE_SCAN_JOB_KIND, status__in=_FINISHED, completed_at__lt=cutoff
    ).delete()
    return deleted
