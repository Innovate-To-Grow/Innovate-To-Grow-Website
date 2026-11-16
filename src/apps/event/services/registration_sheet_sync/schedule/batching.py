"""Durable, per-event batching with short locks independent of provider writes."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import enqueue_job, jobs_enabled
from apps.event.models import Event, RegistrationSheetSyncConfig

from .state import JOB_KIND, QUEUED_STATES, _cancel_pending, _locked_config


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


def _disconnect_destination(event: Event) -> None:
    config = RegistrationSheetSyncConfig.objects.select_for_update().filter(event_id=event.pk).first()
    if config is not None:
        _cancel_pending(config, "Registration sheet destination was disconnected.")
        config.state = config.State.IDLE
        config.save()


def _requeue_pending(config, due_at, now, *, immediate: bool):
    """Move the already-queued job to ``due_at``; None when there is none (or a worker just claimed it)."""
    if not config.pending_job_id:
        return None, due_at
    queued = BackgroundJob.objects.filter(pk=config.pending_job_id, status__in=QUEUED_STATES).first()
    if queued is None:
        return None, due_at
    # Interval mode is a fixed batch boundary; later changes never push
    # it out. A manual Sync now also cannot be postponed by a new edit.
    if config.sync_mode == config.SyncMode.INTERVAL or queued.payload.get("immediate"):
        due_at = min(due_at, queued.available_at)
    payload = {**queued.payload, "immediate": bool(immediate or queued.payload.get("immediate"))}
    updated = BackgroundJob.objects.filter(pk=queued.pk, status__in=QUEUED_STATES).update(
        available_at=due_at, payload=payload, updated_at=now
    )
    return (queued if updated else None), due_at  # Not updated: a worker claimed it while this request waited.


def _run_in_process_after_commit(event: Event, queued, due_at, now) -> None:
    """Without the shared worker, an in-process timer runs the sync once the source change commits."""
    from ..sync.append import _schedule_in_process_sync

    event_id = str(event.pk)
    delay = (due_at - now).total_seconds()
    run_immediately = bool(queued.payload.get("immediate"))
    transaction.on_commit(
        lambda: _schedule_in_process_sync(event_id, delay, run_immediately),
        robust=True,
    )


@transaction.atomic
def schedule_registration_sync(event: Event, *, trigger_id=None, immediate=False):
    """Mark a committed source change and queue it in the same source transaction.

    ``trigger_id`` remains accepted for existing callers. Generations provide
    durable coalescing, rather than one job per registration. Without the
    shared worker, an in-process timer runs the sync after the source commits.
    """
    if not event.registration_sheet_id:
        _disconnect_destination(event)
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

    queued, due_at = _requeue_pending(config, _due_at(config, now, immediate=immediate), now, immediate=immediate)
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
    if not jobs_enabled():
        _run_in_process_after_commit(event, queued, due_at, now)
    return queued
