"""The Message Trace sync in the durable background worker: one outbox job per sync, each queueing the next.

``ensure_scheduled`` (the worker's maintenance: at start-up, then hourly) queues a sync while Message Trace is on and
none is waiting, which restarts the chain if it ever breaks. ``run_now`` (the dashboard's "Sync delivery status now")
only pulls the waiting sync forward: it never queues a second one, and the sender's lease and backoff still apply.
A sync job has one attempt and never raises: the next scheduled sync is its retry, after the interval or the longer
backoff Microsoft's answer asked for. Switching Message Trace off ends the chain after the job in flight.
"""

from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.models import BackgroundJob

from . import limits
from .sync import TraceOutcome, enabled, sync_delivery

DELIVERY_TRACE_JOB_KIND = "core.email_delivery_trace"
_WAITING = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)
_FINISHED = (BackgroundJob.Status.SUCCEEDED, BackgroundJob.Status.FAILED, BackgroundJob.Status.CANCELLED)
FINISHED_JOB_RETENTION = timedelta(days=7)


def register_trace_jobs() -> None:
    """Called from ``CoreConfig.ready``."""
    from apps.core.services.background_jobs import register_job_kind

    register_job_kind(DELIVERY_TRACE_JOB_KIND, handler="apps.core.services.email.graph.tracing.jobs.run_trace_job")


def _jobs(*statuses):
    return BackgroundJob.objects.filter(kind=DELIVERY_TRACE_JOB_KIND, status__in=statuses)


def _enqueue(available_at: datetime, label: str) -> bool:
    from apps.core.services.background_jobs import enqueue_job

    _job, created = enqueue_job(
        kind=DELIVERY_TRACE_JOB_KIND,
        dedupe_key=f"{label}:{available_at.isoformat()}",
        payload={"requested": label},
        max_attempts=1,
        available_at=available_at,
    )
    return created


def ensure_scheduled(*, now: datetime | None = None) -> bool:
    """Queue a sync now unless Message Trace is off or one is waiting or running; True when one was queued."""
    if not enabled() or _jobs(*_WAITING, BackgroundJob.Status.PROCESSING).exists():
        return False
    return _enqueue(now or timezone.now(), "scheduled")


def run_now(*, now: datetime | None = None) -> bool:
    """Make the waiting sync due at once (queueing one when none waits); never while one runs. True when a sync is due
    now."""
    if not enabled() or _jobs(BackgroundJob.Status.PROCESSING).exists():
        return False
    now = now or timezone.now()
    waiting = _jobs(*_WAITING)
    if waiting.exists():
        waiting.filter(available_at__gt=now).update(available_at=now, updated_at=now)
        return True
    return _enqueue(now, "manual")


def next_delay(outcome: TraceOutcome | None) -> int:
    """Seconds until the sync after ``outcome``: the interval, or the longer backoff it asked for."""
    interval = limits.interval_seconds()
    if outcome is None or not outcome.retry_after:
        return interval
    return max(interval, int(outcome.retry_after))


def run_trace_job(job) -> None:
    outcome = None
    try:
        outcome = sync_delivery()
    finally:
        if enabled() and not _jobs(*_WAITING).exists():
            _enqueue(timezone.now() + timedelta(seconds=next_delay(outcome)), "scheduled")


def purge_finished_jobs(*, now: datetime | None = None) -> int:
    """Delete finished sync jobs older than a week (one is queued every interval)."""
    cutoff = (now or timezone.now()) - FINISHED_JOB_RETENTION
    deleted, _ = _jobs(*_FINISHED).filter(completed_at__lt=cutoff).delete()
    return deleted
