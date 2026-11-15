"""Keeping one redirect sync pending at a time: when the next run is requested, folding a new request into a pending
job, and cancelling jobs a newer revision supersedes."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .config import (
    AMPLIFY_REDIRECT_JOB_KIND,
)
from .reconcile import _serialize_scheduling


def _job_requested_at(job):
    value = str((job.payload or {}).get("requested_at") or "")
    requested_at = parse_datetime(value) if value else None
    return requested_at or job.created_at


def _next_requested_at(background_job_model):
    """Return a timestamp strictly newer than every durable revision."""

    requested_at = timezone.now()
    revisions = background_job_model.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).values_list("payload", "created_at")
    for payload, created_at in revisions:
        value = str((payload or {}).get("requested_at") or "")
        candidate = parse_datetime(value) if value else None
        candidate = candidate or created_at
        if candidate >= requested_at:
            requested_at = candidate + timedelta(microseconds=1)
    return requested_at


def _cancel_superseded_jobs(job) -> None:
    """Drop queued revisions provably older than the revision this job represents."""

    from apps.core.models import BackgroundJob

    requested_at = _job_requested_at(job)
    with transaction.atomic(), _serialize_scheduling():
        candidates = list(
            BackgroundJob.objects.select_for_update()
            .filter(
                kind=AMPLIFY_REDIRECT_JOB_KIND,
                status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY],
            )
            .exclude(pk=job.pk)
        )
        # Equal timestamps are deliberately kept. Database timestamps have
        # finite precision, so equality cannot prove which serialized request
        # is newer; an extra idempotent reconcile is safer than dropping one.
        superseded_ids = [candidate.pk for candidate in candidates if _job_requested_at(candidate) < requested_at]
        if superseded_ids:
            now = timezone.now()
            BackgroundJob.objects.filter(pk__in=superseded_ids).update(
                status=BackgroundJob.Status.CANCELLED,
                completed_at=now,
                last_error="Superseded by a newer full Amplify redirect reconciliation.",
                updated_at=now,
            )


def _newer_revision_exists(job) -> bool:
    """Check for a later full-state request while holding the provider lock."""

    from apps.core.models import BackgroundJob

    requested_at = _job_requested_at(job)
    candidates = BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).exclude(pk=job.pk)
    return any(_job_requested_at(candidate) > requested_at for candidate in candidates)


def _cancel_current_superseded_job(job) -> bool:
    """Relinquish this claim without letting the generic worker mark success."""

    from apps.core.models import BackgroundJob

    now = timezone.now()
    updated = BackgroundJob.objects.filter(
        pk=job.pk,
        status=BackgroundJob.Status.PROCESSING,
        claim_token=job.claim_token,
    ).update(
        status=BackgroundJob.Status.CANCELLED,
        completed_at=now,
        claim_token=None,
        claimed_at=None,
        last_error="Superseded by a newer full Amplify redirect reconciliation.",
        updated_at=now,
    )
    if updated:
        job.status = BackgroundJob.Status.CANCELLED
        job.completed_at = now
        job.claim_token = None
        job.claimed_at = None
    return bool(updated)


def _coalesce_into(queued, payload, requested_redirect_ids, available_at):
    """Fold this request into the already-queued sync: union the redirect ids and restart it from pending."""
    from apps.core.models import BackgroundJob

    requested_redirect_ids = requested_redirect_ids | set((queued.payload or {}).get("requested_redirect_ids") or [])
    payload["requested_redirect_ids"] = sorted(requested_redirect_ids)
    queued.status = BackgroundJob.Status.PENDING
    queued.payload = payload
    queued.available_at = available_at
    queued.attempts = 0
    queued.completed_at = None
    queued.last_error = ""
    queued.save(
        update_fields=["status", "payload", "available_at", "attempts", "completed_at", "last_error", "updated_at"]
    )
    return queued
