"""The ingest in the durable background worker: job kind ``helpdesk.ingest_inbound``, polling only (no webhooks).

``core``'s mailbox scan (every ``inbox_scan_interval_seconds`` while the helpdesk is on) records new mail and queues
this job by name (the helpdesk registers it as the inbound queue's consumer). A run drains what is due within its
budget and queues the next one: at once when it stopped at the budget, at Microsoft's Retry-After when throttled,
at the next row's retry time otherwise. ``ensure_scheduled`` (the worker's hourly maintenance) restarts the chain if
it broke. While a campaign is sending (and ``pause_while_campaign_sending`` is on) a run only queues itself for
later: reads and sends share Outlook's per-mailbox limits. The job has no delivery family: it sends nothing.
"""

from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.email.inbound import consume
from apps.mail.models import EmailCampaign

from ...models import HelpdeskSettings
from . import runner

INGEST_JOB_KIND = "helpdesk.ingest_inbound"
CONTINUE_SECONDS = 5
CAMPAIGN_PAUSE_SECONDS = 120
FINISHED_JOB_RETENTION = timedelta(days=7)
_WAITING = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)
_FINISHED = (BackgroundJob.Status.SUCCEEDED, BackgroundJob.Status.FAILED, BackgroundJob.Status.CANCELLED)


def register_ingest() -> None:
    """Called from ``HelpdeskConfig.ready``."""
    from apps.core.services.background_jobs import register_job_kind
    from apps.core.services.email.inbound import register_inbound_consumer

    register_job_kind(INGEST_JOB_KIND, handler="apps.helpdesk.services.ingest.jobs.run_ingest_job")
    register_inbound_consumer(INGEST_JOB_KIND, active="apps.helpdesk.services.ingest.jobs.ingest_enabled")


def ingest_enabled() -> bool:
    return bool(HelpdeskSettings.load().enabled)


def campaign_sending() -> bool:
    return EmailCampaign.objects.filter(status="sending").exists()


def _waiting() -> bool:
    return BackgroundJob.objects.filter(kind=INGEST_JOB_KIND, status__in=_WAITING).exists()


def _enqueue(available_at: datetime, label: str) -> bool:
    from apps.core.services.background_jobs import enqueue_job

    _job, created = enqueue_job(
        kind=INGEST_JOB_KIND,
        dedupe_key=f"{label}:{available_at.isoformat()}",
        payload={"requested": label},
        max_attempts=1,
        available_at=available_at,
    )
    return created


def next_run_at(outcome: runner.RunOutcome, *, now: datetime) -> datetime | None:
    """When the run after ``outcome`` should start; None when nothing waits (the next scan queues one)."""
    if outcome.stopped in ("disabled", "no_reader"):
        return None  # the hourly maintenance looks again
    if outcome.busy_until is not None:
        return outcome.busy_until
    if outcome.stopped in ("budget", "time"):
        return now + timedelta(seconds=CONTINUE_SECONDS)
    due = consume.next_due_at(now=now)
    return max(due, now) if due is not None else None


def run_ingest_job(job) -> None:
    settings = HelpdeskSettings.load()
    if not settings.enabled:
        return
    now = timezone.now()
    if settings.pause_while_campaign_sending and campaign_sending():
        if not _waiting():
            _enqueue(now + timedelta(seconds=CAMPAIGN_PAUSE_SECONDS), "campaign-pause")
        return
    outcome = runner.run(settings)
    at = next_run_at(outcome, now=timezone.now())
    if at is not None and not _waiting():
        _enqueue(at, "chain")


def ensure_scheduled(*, now: datetime | None = None) -> bool:
    """Queue an ingest run when mail waits and none is queued or running (the worker's maintenance)."""
    settings = HelpdeskSettings.load()
    if not settings.enabled:
        return False
    now = now or timezone.now()
    consume.recover_stale(stale_after=runner.stale_after(settings), max_attempts=int(settings.max_attempts), now=now)
    if BackgroundJob.objects.filter(
        kind=INGEST_JOB_KIND, status__in=(*_WAITING, BackgroundJob.Status.PROCESSING)
    ).exists():
        return False
    due = consume.next_due_at(now=now)
    return _enqueue(max(due, now), "scheduled") if due is not None else False


def purge_finished_jobs(*, now: datetime | None = None) -> int:
    """Delete finished ingest jobs older than a week."""
    cutoff = (now or timezone.now()) - FINISHED_JOB_RETENTION
    deleted, _ = BackgroundJob.objects.filter(
        kind=INGEST_JOB_KIND, status__in=_FINISHED, completed_at__lt=cutoff
    ).delete()
    return deleted
