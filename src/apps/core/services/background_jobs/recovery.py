import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.models import BackgroundJob

from .registry import notify_job_state, resolve_stale_job_state

logger = logging.getLogger(__name__)


def recover_stale_jobs(*, stale_after: timedelta = timedelta(minutes=10)) -> dict[str, int]:
    """Recover abandoned claims without automatically duplicating deliveries."""
    cutoff = timezone.now() - stale_after
    now = timezone.now()
    with transaction.atomic():
        queryset = BackgroundJob.objects.select_for_update().filter(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at__lt=cutoff,
        )
        retry_ids = []
        failed_ids = []
        uncertain_ids = []
        completed_ids = []
        for job in queryset:
            resolved_state = resolve_stale_job_state(job)
            if resolved_state == BackgroundJob.Status.SUCCEEDED:
                completed_ids.append(job.pk)
            elif resolved_state == BackgroundJob.Status.RETRY:
                retry_ids.append(job.pk)
            elif resolved_state == BackgroundJob.Status.FAILED:
                failed_ids.append(job.pk)
            elif resolved_state == BackgroundJob.Status.UNCERTAIN:
                uncertain_ids.append(job.pk)
            elif job.can_retry_after_claim or job.provider_call_started_at is None:
                retry_ids.append(job.pk)
            else:
                uncertain_ids.append(job.pk)
        if completed_ids:
            BackgroundJob.objects.filter(pk__in=completed_ids).update(
                status=BackgroundJob.Status.SUCCEEDED,
                claim_token=None,
                claimed_at=None,
                completed_at=now,
                last_error="",
                updated_at=now,
            )
        if retry_ids:
            BackgroundJob.objects.filter(pk__in=retry_ids).update(
                status=BackgroundJob.Status.RETRY,
                available_at=now,
                claim_token=None,
                claimed_at=None,
                provider_call_started_at=None,
                last_error="Worker claim expired before completion.",
                updated_at=now,
            )
        if uncertain_ids:
            BackgroundJob.objects.filter(pk__in=uncertain_ids).update(
                status=BackgroundJob.Status.UNCERTAIN,
                claim_token=None,
                claimed_at=None,
                completed_at=now,
                last_error=(
                    "Worker stopped after the provider call began; delivery outcome is uncertain. "
                    "Review before manually retrying."
                ),
                updated_at=now,
            )
        if failed_ids:
            BackgroundJob.objects.filter(pk__in=failed_ids).update(
                status=BackgroundJob.Status.FAILED,
                claim_token=None,
                claimed_at=None,
                completed_at=now,
                last_error="Provider definitively rejected the delivery.",
                updated_at=now,
            )
        recovered_ids = [*completed_ids, *retry_ids, *failed_ids, *uncertain_ids]
    # Domain mirrors are best-effort and deliberately run after the durable job
    # transition commits. A database error in a mirror must not roll back the
    # outbox recovery transaction.
    for job in BackgroundJob.objects.filter(pk__in=recovered_ids):
        try:
            notify_job_state(job)
        except Exception:  # noqa: BLE001 - generic recovery must continue.
            logger.exception("Unable to mirror recovered state for background job %s", job.pk)
    return {
        "completed": len(completed_ids),
        "retried": len(retry_ids),
        "failed": len(failed_ids),
        "uncertain": len(uncertain_ids),
    }
