import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MEMBER_SHEET_JOB_KIND = "authn.member_sheet_sync"
DEBOUNCE_SECONDS = 15


def schedule_member_sync() -> None:
    from apps.authn.models import MemberSheetSyncConfig

    config = MemberSheetSyncConfig.load()
    if not config.is_configured or not config.auto_sync_enabled:
        return

    from apps.core.services.background_jobs import jobs_enabled

    if jobs_enabled():
        _enqueue_durable_sync(immediate=False)
    else:
        # Expand-first rollout fallback. This is intentionally synchronous so
        # work cannot disappear when a web process exits.
        _flush_pending_sync()


def schedule_immediate_sync() -> None:
    from apps.core.services.background_jobs import jobs_enabled

    if jobs_enabled():
        _enqueue_durable_sync(immediate=True)
    else:
        _flush_pending_sync()


def _enqueue_durable_sync(*, immediate: bool):
    """Coalesce queued full-sync work without losing writes during a claim."""
    from apps.core.models import BackgroundJob
    from apps.core.services.background_jobs import enqueue_job

    available_at = timezone.now()
    if not immediate:
        available_at += timedelta(seconds=DEBOUNCE_SECONDS)

    with transaction.atomic():
        queued = (
            BackgroundJob.objects.select_for_update()
            .filter(
                kind=MEMBER_SHEET_JOB_KIND,
                status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY],
            )
            .order_by("created_at")
            .first()
        )
        if queued is not None:
            queued.available_at = available_at
            queued.last_error = ""
            queued.save(update_fields=["available_at", "last_error", "updated_at"])
            return queued
        job, _created = enqueue_job(
            kind=MEMBER_SHEET_JOB_KIND,
            dedupe_key=str(uuid.uuid4()),
            payload={},
            can_retry_after_claim=True,
            available_at=available_at,
        )
        return job


def _flush_pending_sync(*, raise_errors: bool = False) -> None:
    try:
        from apps.authn.models import MemberSheetSyncLog
        from apps.authn.services.member_sheet_sync import sync_members_to_sheet

        sync_members_to_sheet(sync_type=MemberSheetSyncLog.SyncType.DEBOUNCED)
    except Exception:
        logger.exception("Member sheet sync failed.")
        if raise_errors:
            raise
