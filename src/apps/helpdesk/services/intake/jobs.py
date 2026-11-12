"""The intake in the durable background worker: job kind ``helpdesk.intake_scan``, one job per scan, each queueing
the next. Polling only (no webhooks); it sends nothing, so the job has no delivery family.

Every ``inbox_scan_interval_seconds`` (2 minutes) a scan lists the Inbox from the helpdesk's own checkpoint; a scan
that recorded new mail wakes the ingest, which makes the tickets. A scan that stopped at its page or time budget
continues sooner (catching up), a throttle waits as long as Microsoft asked, and a paused intake keeps its chain (each
scan finds it paused and does nothing). ``ensure_scheduled`` (the worker's maintenance, at start-up and hourly, and
saving Helpdesk → Settings) restarts the chain if it broke; ``run_now`` is the card's "Scan now". While the helpdesk is
switched off nothing is queued. A job has one attempt: the next scan is its retry. Overlapping jobs are harmless: the
mailbox lease lets only one scan run. ``interval_seconds`` and ``catch_up_seconds`` are what both cards show.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.models import BackgroundJob

from ...models import HelpdeskSettings
from ..ingest import jobs as ingest_jobs

INTAKE_JOB_KIND = "helpdesk.intake_scan"
# A scan that stopped at its page or time budget continues this soon (sooner than the interval, never later): it only
# lists and records, so catching up after a "Rescan since" costs a few list requests a minute.
_CATCH_UP_SECONDS = 30
_WAITING = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)
_FINISHED = (BackgroundJob.Status.SUCCEEDED, BackgroundJob.Status.FAILED, BackgroundJob.Status.CANCELLED)
FINISHED_JOB_RETENTION = timedelta(days=7)


def register_intake() -> None:
    """Called from ``HelpdeskConfig.ready``: the job kind, and the description the Email Monitoring card shows."""
    from apps.core.services.background_jobs import register_job_kind
    from apps.core.services.email.inbound import register_inbox_reader

    register_job_kind(INTAKE_JOB_KIND, handler="apps.helpdesk.services.intake.jobs.run_intake_job")
    register_inbox_reader("helpdesk", describe="apps.helpdesk.services.intake.status.describe")


def interval_seconds() -> int:
    """Seconds between two scans: ``inbox_scan_interval_seconds``, never under a minute."""
    return max(60, int(settings.EMAIL_MONITORING["inbox_scan_interval_seconds"]))


def catch_up_seconds() -> int:
    """Seconds until the scan after one that stopped at its budget."""
    return min(interval_seconds(), _CATCH_UP_SECONDS)


def enabled() -> bool:
    return bool(HelpdeskSettings.load().enabled)


def _waiting(*statuses) -> bool:
    return BackgroundJob.objects.filter(kind=INTAKE_JOB_KIND, status__in=(*_WAITING, *statuses)).exists()


def _enqueue(available_at: datetime, label: str) -> bool:
    """Queue one scan. Callers first check that none is waiting; two workers racing past that check queue two, and
    the chain still continues as one: a scan that finds another waiting queues no successor."""
    from apps.core.services.background_jobs import enqueue_job

    _job, created = enqueue_job(
        kind=INTAKE_JOB_KIND,
        dedupe_key=f"{label}:{available_at.isoformat()}",
        payload={"requested": label},
        max_attempts=1,
        available_at=available_at,
    )
    return created


def ensure_scheduled(*, now: datetime | None = None) -> bool:
    """Queue a scan now unless one is waiting or running; True when one was queued."""
    if not enabled() or _waiting(BackgroundJob.Status.PROCESSING):
        return False
    return _enqueue(now or timezone.now(), "scheduled")


def run_now(*, now: datetime | None = None) -> bool:
    """Queue a scan to run at once (the card's "Scan now"); False while the helpdesk is switched off."""
    if not enabled():
        return False
    return _enqueue(now or timezone.now(), "manual")


def next_delay(outcome) -> int:
    """Seconds until the scan after ``outcome``: the interval, sooner to catch up, later when Microsoft asked."""
    interval = interval_seconds()
    if outcome is None:
        return interval
    if outcome.retry_after:
        return max(interval, int(outcome.retry_after))
    return catch_up_seconds() if outcome.status == "partial" else interval


def run_intake_job(job) -> None:
    from .scanner import scan_inbox

    outcome = None
    try:
        outcome = scan_inbox()
        if outcome.stats.get("recorded"):
            ingest_jobs.wake()
    finally:
        if enabled() and not _waiting():
            _enqueue(timezone.now() + timedelta(seconds=next_delay(outcome)), "scheduled")


def purge_finished_jobs(*, now: datetime | None = None) -> int:
    """Delete finished scan jobs older than a week (one is queued every interval)."""
    cutoff = (now or timezone.now()) - FINISHED_JOB_RETENTION
    deleted, _ = BackgroundJob.objects.filter(
        kind=INTAKE_JOB_KIND, status__in=_FINISHED, completed_at__lt=cutoff
    ).delete()
    return deleted
