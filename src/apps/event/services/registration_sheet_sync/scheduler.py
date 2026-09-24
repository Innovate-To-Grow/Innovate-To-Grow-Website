"""Durable, per-event batching with short locks independent of provider writes."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import enqueue_job
from apps.event.models import Event, RegistrationSheetSyncConfig

JOB_KIND = "event.registration_sheet_sync"
QUEUED_STATES = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)


def _locked_config(event_id):
    RegistrationSheetSyncConfig.objects.get_or_create(event_id=event_id)
    return RegistrationSheetSyncConfig.objects.select_for_update().get(event_id=event_id)


def _due_at(config, now, *, immediate):
    if immediate:
        return now
    if config.sync_mode == config.SyncMode.INTERVAL:
        anchor = config.last_success_at or config.first_dirty_at or now
        return max(now, anchor + timedelta(minutes=config.interval_minutes))
    first_dirty = config.first_dirty_at or now
    return min(
        now + timedelta(seconds=config.debounce_seconds), first_dirty + timedelta(seconds=config.max_delay_seconds)
    )


def _cancel_pending(config, reason):
    if config.pending_job_id:
        BackgroundJob.objects.filter(pk=config.pending_job_id, status__in=QUEUED_STATES).update(
            status=BackgroundJob.Status.CANCELLED,
            completed_at=timezone.now(),
            last_error=reason,
            updated_at=timezone.now(),
        )
    config.pending_job = None
    config.next_sync_at = None


@transaction.atomic
def schedule_registration_sync(event: Event, *, trigger_id=None, immediate=False):
    """Mark a committed source change and queue it in the same source transaction.

    ``trigger_id`` remains accepted for existing callers. Generations provide
    durable coalescing, rather than one job per registration. The shared worker
    must be running; this function never starts an in-process provider thread.
    """
    if not event.registration_sheet_id:
        config = RegistrationSheetSyncConfig.objects.select_for_update().filter(event_id=event.pk).first()
        if config is not None:
            _cancel_pending(config, "Registration sheet destination was disconnected.")
            config.state = config.State.IDLE
            config.save()
        return None
    config = _locked_config(event.pk)
    now = timezone.now()
    config.requested_generation += 1
    config.last_dirty_at = now
    if config.first_dirty_at is None:
        config.first_dirty_at = now
    if not immediate and config.sync_mode == config.SyncMode.MANUAL:
        _cancel_pending(config, "Automatic sync disabled; changes remain pending for manual sync.")
        if config.state != config.State.RUNNING:
            config.state = config.State.IDLE
        config.save()
        return None
    if not immediate and config.state == config.State.BLOCKED:
        config.save()
        return None

    due_at = _due_at(config, now, immediate=immediate)
    queued = None
    if config.pending_job_id:
        queued = BackgroundJob.objects.filter(pk=config.pending_job_id, status__in=QUEUED_STATES).first()
        if queued is not None:
            # Interval mode is a fixed batch boundary; later changes never push
            # it out. A manual Sync now also cannot be postponed by a new edit.
            if config.sync_mode == config.SyncMode.INTERVAL or queued.payload.get("immediate"):
                due_at = min(due_at, queued.available_at)
            payload = {**queued.payload, "immediate": bool(immediate or queued.payload.get("immediate"))}
            updated = BackgroundJob.objects.filter(pk=queued.pk, status__in=QUEUED_STATES).update(
                available_at=due_at, payload=payload, updated_at=now
            )
            if not updated:
                queued = None  # A worker claimed it while this request waited.
    if queued is None:
        queued, _ = enqueue_job(
            kind=JOB_KIND,
            dedupe_key=f"{event.pk}:{uuid.uuid4()}",
            payload={"event_id": str(event.pk), "immediate": bool(immediate)},
            available_at=due_at,
            can_retry_after_claim=True,
        )
    config.pending_job = queued
    config.next_sync_at = due_at
    config.state = config.State.SCHEDULED
    config.last_error = ""
    config.save()
    queued.refresh_from_db()
    return queued


@transaction.atomic
def begin_sync(event_id, job=None):
    """Capture a generation before taking any long-lived provider/event lock."""
    config = _locked_config(event_id)
    if job is not None:
        if not BackgroundJob.objects.filter(
            pk=job.pk, status=BackgroundJob.Status.PROCESSING, claim_token=job.claim_token
        ).exists():
            from apps.core.services.background_jobs import JobClaimLost

            raise JobClaimLost("Registration sheet sync job is no longer owned by this worker.")
    if config.requested_generation <= config.completed_generation:
        config.requested_generation += 1
    if job is None:
        _cancel_pending(config, "Superseded by an explicit registration sheet sync.")
    if job is None or config.pending_job_id == job.pk:
        config.pending_job = None
        config.next_sync_at = None
        config.first_dirty_at = None
    config.state = config.State.RUNNING
    config.last_attempt_at = timezone.now()
    config.last_error = ""
    config.save()
    return {"config": config, "captured_generation": config.requested_generation}


@transaction.atomic
def complete_sync(event_id, generation, *, added=0, updated=0, deleted=0, header_changes=0, unchanged=0, conflicts=0):
    """Acknowledge only the captured generation; retain changes made during I/O."""
    config = _locked_config(event_id)
    if generation < config.completed_generation:
        return config
    config.completed_generation = min(generation, config.requested_generation)
    config.last_success_at = timezone.now()
    config.last_error = ""
    config.last_added_count = added
    config.last_updated_count = updated
    config.last_unchanged_count = unchanged
    config.last_conflict_count = conflicts
    config.last_deleted_count = deleted
    config.last_header_changes_count = header_changes
    if config.completed_generation >= config.requested_generation:
        _cancel_pending(config, "Changes were included in the completed sheet sync.")
        config.first_dirty_at = None
        config.state = config.State.SUCCEEDED
    else:
        config.state = config.State.SCHEDULED if config.pending_job_id else config.State.IDLE
    config.save()
    return config


@transaction.atomic
def fail_sync(event_id, generation, error, *, blocked=False, conflicts=0):
    config = _locked_config(event_id)
    if generation <= config.completed_generation:
        return config
    config.last_error = str(error)
    config.last_conflict_count = conflicts
    config.state = config.State.BLOCKED if blocked else config.State.FAILED
    if blocked:
        _cancel_pending(config, "Sheet sync requires review before automatic work can continue.")
    config.save()
    return config


@transaction.atomic
def mirror_job_state(job):
    """Reflect worker retry/exhaustion without losing a newer queued change."""
    event_id = job.payload.get("event_id")
    config = RegistrationSheetSyncConfig.objects.select_for_update().filter(event_id=event_id).first()
    if config is None or config.completed_generation >= config.requested_generation:
        return
    if config.pending_job_id and config.pending_job_id != job.pk:
        return
    if job.status == BackgroundJob.Status.RETRY and config.state != config.State.BLOCKED:
        config.pending_job = job
        config.next_sync_at = job.available_at
        config.state = config.State.SCHEDULED
    elif job.status in (BackgroundJob.Status.FAILED, BackgroundJob.Status.UNCERTAIN):
        config.pending_job = None
        config.next_sync_at = None
        if config.state != config.State.BLOCKED:
            config.state = config.State.FAILED
    else:
        return
    config.last_error = job.last_error
    config.save()


def job_should_run(job):
    event_id = job.payload.get("event_id")
    if not Event.objects.filter(pk=event_id).exclude(registration_sheet_id="").exists():
        return False
    config = RegistrationSheetSyncConfig.objects.filter(event_id=event_id).first()
    if config is None:
        return True
    if config.completed_generation >= config.requested_generation:
        return False
    if job.payload.get("immediate"):
        return True
    return config.sync_mode != config.SyncMode.MANUAL and config.state != config.State.BLOCKED
