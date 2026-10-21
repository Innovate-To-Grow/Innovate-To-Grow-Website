"""Background-job handler for the full member-sheet sync."""

from django.db import transaction
from django.utils import timezone


def sync_member_sheet_job(job) -> None:
    """Run one full member sync and collapse older queued snapshots."""
    from apps.authn.services.members.sheet_sync import _flush_pending_sync
    from apps.authn.services.members.sheet_sync.scheduler import MEMBER_SHEET_JOB_KIND
    from apps.core.models import BackgroundJob

    # Changes committed after this job was claimed create a distinct follow-up
    # job. Only older queued work is redundant with the snapshot about to run.
    with transaction.atomic():
        BackgroundJob.objects.filter(
            kind=MEMBER_SHEET_JOB_KIND,
            status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY],
            created_at__lte=job.claimed_at or timezone.now(),
        ).exclude(pk=job.pk).update(
            status=BackgroundJob.Status.CANCELLED,
            completed_at=timezone.now(),
            last_error="Superseded by a newer full member-sheet snapshot.",
            updated_at=timezone.now(),
        )
    _flush_pending_sync(raise_errors=True)
