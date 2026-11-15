import logging
import math
import random
from datetime import timedelta
from enum import StrEnum

from django.db import connection, transaction
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.delivery_rates import WaitMode, wait_mode
from apps.core.services.delivery_rates.rules.defaults import section
from apps.core.services.email.telemetry.context import job_tracking

from .errors import (
    DeferredJobError,
    JobClaimLost,
    PermanentJobError,
    TransientJobError,
    UncertainJobError,
    exception_chain,
    is_known_transient,
    safe_error,
)
from .gating import blocked_job_kinds
from .registry import get_handler, notify_job_state

logger = logging.getLogger(__name__)

__all__ = [
    "DeferredJobError",
    "JobClaimLost",
    "JobOutcome",
    "PermanentJobError",
    "TransientJobError",
    "UncertainJobError",
    "claim_jobs",
    "process_claimed_job",
    "run_claimed_job",
]


class JobOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    # Held back by its delivery lane before any provider call; due again at its slot, no attempt used.
    DEFERRED = "deferred"


def _retry_delay(attempts: int, chain) -> int:
    """Exponential backoff (``DELIVERY_RATES["jobs"]``), stretched to any Retry-After the provider asked for."""
    jobs = section("jobs")
    ceiling = jobs["retry_max_seconds"]
    backoff = min(ceiling, 2 ** max(0, attempts - 1) * jobs["retry_base_seconds"])
    hinted = max((item.retry_after or 0 for item in chain if isinstance(item, TransientJobError)), default=0)
    return min(ceiling, max(backoff, math.ceil(hinted)))


def claim_jobs(*, batch_size: int = 10) -> list[BackgroundJob]:
    """Atomically claim an available batch using SKIP LOCKED on PostgreSQL.

    Lower priorities go first (login codes and tickets before campaigns), then the longest-due jobs. Kinds whose
    delivery lane is paced, cooling down or stopped are left for later, so a waiting campaign never makes a worker
    claim and defer job after job.
    """
    now = timezone.now()
    blocked = blocked_job_kinds()
    with transaction.atomic():
        queryset = BackgroundJob.objects.filter(
            status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY],
            available_at__lte=now,
        )
        if blocked:
            queryset = queryset.exclude(kind__in=blocked)
        queryset = queryset.order_by("priority", "available_at", "created_at")
        if connection.features.has_select_for_update:
            queryset = queryset.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
        jobs = list(queryset[: max(1, batch_size)])
        for job in jobs:
            job.status = BackgroundJob.Status.PROCESSING
            job.claim_token = BackgroundJob.new_claim_token()
            job.claimed_at = now
            job.provider_call_started_at = None
            job.attempts += 1
            job.last_error = ""
            job.save(
                update_fields=[
                    "status",
                    "claim_token",
                    "claimed_at",
                    "provider_call_started_at",
                    "attempts",
                    "last_error",
                    "updated_at",
                ]
            )
        return jobs


def _complete(job: BackgroundJob) -> None:
    now = timezone.now()
    updated = BackgroundJob.objects.filter(
        pk=job.pk,
        status=BackgroundJob.Status.PROCESSING,
        claim_token=job.claim_token,
    ).update(
        status=BackgroundJob.Status.SUCCEEDED,
        completed_at=now,
        claim_token=None,
        claimed_at=None,
        last_error="",
        updated_at=now,
    )
    if updated:
        job.refresh_from_db()
        try:
            notify_job_state(job)
        except Exception:  # noqa: BLE001 - mirror failure must not kill the worker.
            logger.exception("Unable to mirror completed state for background job %s", job.pk)


def _deferral(job: BackgroundJob, chain) -> dict | None:
    """The retry of a job its delivery lane held back before any provider call: at its slot, attempt refunded."""
    deferred = next((item for item in chain if isinstance(item, DeferredJobError)), None)
    if deferred is None or job.provider_call_started_at is not None:
        return None
    # Spreads deferred retries only; nothing secret depends on it.
    jitter = random.uniform(0, section("jobs")["defer_jitter_seconds"])  # noqa: S311  # nosec B311
    return {
        "status": BackgroundJob.Status.RETRY,
        "available_at": deferred.until + timedelta(seconds=jitter),
        "attempts": max(0, job.attempts - 1),
    }


def _failure_target(job: BackgroundJob, exc: BaseException, chain, now) -> dict:
    """The status (and retry time) a failed job moves to."""
    retry = {"status": BackgroundJob.Status.RETRY}
    keep = {"available_at": job.available_at}
    if any(isinstance(item, TransientJobError) for item in chain):
        if job.attempts < job.max_attempts:
            return {**retry, "available_at": now + timedelta(seconds=_retry_delay(job.attempts, chain))}
        return {"status": BackgroundJob.Status.FAILED, **keep}
    if any(isinstance(item, PermanentJobError) for item in chain):
        return {"status": BackgroundJob.Status.FAILED, **keep}
    uncertain = any(isinstance(item, UncertainJobError) for item in chain)
    if uncertain or (job.provider_call_started_at is not None and not job.can_retry_after_claim):
        return {"status": BackgroundJob.Status.UNCERTAIN, **keep}
    if is_known_transient(exc) and job.attempts < job.max_attempts:
        return {**retry, "available_at": now + timedelta(seconds=_retry_delay(job.attempts, chain))}
    return {"status": BackgroundJob.Status.FAILED, **keep}


def _fail(job: BackgroundJob, exc: BaseException) -> JobOutcome:
    job.refresh_from_db(fields=["provider_call_started_at", "attempts", "max_attempts"])
    now = timezone.now()
    chain = tuple(exception_chain(exc))
    deferral = _deferral(job, chain)
    target = deferral or _failure_target(job, exc, chain, now)
    terminal = target["status"] in {BackgroundJob.Status.FAILED, BackgroundJob.Status.UNCERTAIN}
    updated = BackgroundJob.objects.filter(
        pk=job.pk,
        status=BackgroundJob.Status.PROCESSING,
        claim_token=job.claim_token,
    ).update(
        **target,
        completed_at=now if terminal else None,
        claim_token=None,
        claimed_at=None,
        last_error=safe_error(exc),
        updated_at=now,
    )
    if updated:
        job.refresh_from_db()
        try:
            notify_job_state(job)
        except Exception:  # noqa: BLE001 - mirror failure must not kill the worker.
            logger.exception("Unable to mirror failed state for background job %s", job.pk)
    return JobOutcome.DEFERRED if deferral else JobOutcome.FAILED


def run_claimed_job(job: BackgroundJob) -> JobOutcome:
    """Run one claimed job. Delivery handlers wait for their slot as the worker does (``WaitMode.WORKER``)."""
    try:
        with wait_mode(WaitMode.WORKER), job_tracking(job):
            get_handler(job.kind)(job)
    except Exception as exc:  # noqa: BLE001 - job boundary must persist every failure.
        if any(isinstance(item, DeferredJobError) for item in exception_chain(exc)):
            logger.info("Background job %s (%s) deferred by its delivery rate", job.pk, job.kind)
        else:
            logger.exception("Background job %s (%s) failed", job.pk, job.kind)
        return _fail(job, exc)
    _complete(job)
    return JobOutcome.SUCCEEDED


def process_claimed_job(job: BackgroundJob) -> bool:
    """Run one claimed job; True when it succeeded."""
    return run_claimed_job(job) == JobOutcome.SUCCEEDED
