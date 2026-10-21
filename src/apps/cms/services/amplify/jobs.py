"""Durable scheduling of full reconciliations: coalescing, supersession, retries and status mirroring."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import reconcile
from .config import (
    AMPLIFY_CONFIGURATION_PAYLOAD_KEY,
    AMPLIFY_REDIRECT_JOB_KIND,
    _configured_app_id,
    _latest_known_amplify_configuration,
)
from .errors import AmplifyRedirectConfigurationError
from .reconcile import _is_transient_amplify_error, _serialize_reconciliations, _serialize_scheduling

AMPLIFY_REDIRECT_DEBOUNCE_SECONDS = 2


def _job_requested_at(job):
    value = str((job.payload or {}).get("requested_at") or "")
    requested_at = parse_datetime(value) if value else None
    return requested_at or job.created_at


def _job_attempt_started_at(job):
    value = str((job.payload or {}).get("attempt_started_at") or "")
    return parse_datetime(value) if value else None


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


def sync_amplify_redirects_job(job) -> None:
    """Background-job handler with retry-safe AWS error classification."""

    from apps.cms.models import RouteRedirect
    from apps.core.models import BackgroundJob
    from apps.core.services.background_jobs import JobClaimLost, PermanentJobError, TransientJobError

    _cancel_superseded_jobs(job)
    # The provider lock serializes writes, while this in-lock revision gate
    # prevents a previously claimed older job from running after a newer job
    # has already won the lock. Serialization alone does not imply FIFO.
    reconcile_error: Exception | None = None
    with _serialize_reconciliations():
        if _newer_revision_exists(job):
            if not _cancel_current_superseded_job(job):
                raise JobClaimLost("Background job claim was lost before supersession.")
            return

        requested_at = _job_requested_at(job)
        attempt_started_at = timezone.now()
        payload = {**(job.payload or {}), "attempt_started_at": attempt_started_at.isoformat()}
        owns_claim = BackgroundJob.objects.filter(
            pk=job.pk,
            status=BackgroundJob.Status.PROCESSING,
            claim_token=job.claim_token,
        ).update(payload=payload, updated_at=attempt_started_at)
        if not owns_claim:
            raise JobClaimLost("Background job claim was lost before Amplify reconciliation.")
        job.payload = payload

        requested_ids = payload.get("requested_redirect_ids") or []
        eligible = Q(is_active=True) | Q(edge_rule_managed=True)
        if requested_ids:
            eligible |= Q(pk__in=requested_ids)
        RouteRedirect.objects.filter(updated_at__lte=requested_at).filter(eligible).update(
            edge_sync_attempted_at=attempt_started_at
        )
        try:
            # reconcile_amplify_redirects reacquires the transaction-scoped
            # advisory lock on the same connection. PostgreSQL permits this,
            # and direct callers retain the same serialization guarantee.
            reconcile.reconcile_amplify_redirects(configuration=payload.get(AMPLIFY_CONFIGURATION_PAYLOAD_KEY))
        except Exception as exc:
            # Leave the provider-lock transaction normally so the durable
            # attempt marker commits even when the nested reconciliation
            # savepoint rolls back. The worker can then mirror pending/failed
            # state using that token after we re-raise outside the lock.
            reconcile_error = exc

    if isinstance(reconcile_error, AmplifyRedirectConfigurationError):
        raise PermanentJobError(str(reconcile_error)) from reconcile_error
    if reconcile_error is not None:
        if _is_transient_amplify_error(reconcile_error):
            raise TransientJobError("AWS Amplify is temporarily unavailable.") from reconcile_error
        if isinstance(reconcile_error, BotoCoreError | ClientError):
            raise PermanentJobError("AWS Amplify rejected the redirect reconciliation.") from reconcile_error
        raise reconcile_error


def sync_amplify_redirect_job_state(job) -> None:
    """Mirror durable job state to redirects included in that request revision."""

    from apps.cms.models import RouteRedirect
    from apps.core.models import BackgroundJob

    attempt_started_at = _job_attempt_started_at(job)
    if attempt_started_at is None:
        return
    queryset = RouteRedirect.objects.filter(
        updated_at__lte=_job_requested_at(job),
        edge_sync_attempted_at=attempt_started_at,
    )
    if job.status == BackgroundJob.Status.SUCCEEDED:
        queryset.update(
            edge_sync_status="synced",
            edge_sync_error="",
            edge_synced_at=job.completed_at or timezone.now(),
        )
    elif job.status in {BackgroundJob.Status.FAILED, BackgroundJob.Status.UNCERTAIN}:
        queryset.update(
            edge_sync_status="failed",
            edge_sync_error=(job.last_error or "Amplify redirect reconciliation failed.")[:500],
        )
    elif job.status in {
        BackgroundJob.Status.PENDING,
        BackgroundJob.Status.PROCESSING,
        BackgroundJob.Status.RETRY,
    }:
        queryset.update(
            edge_sync_status="pending",
            edge_sync_error=(job.last_error or "")[:500],
        )


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


def schedule_amplify_redirect_sync(*, immediate: bool = False, redirect_ids=()):
    """Coalesce a durable full reconciliation, or leave status pending if disabled."""

    from apps.core.models import BackgroundJob
    from apps.core.services.background_jobs import enqueue_job, jobs_enabled

    if not _configured_app_id() or not jobs_enabled():
        return None

    requested_redirect_ids = {str(redirect_id) for redirect_id in redirect_ids}

    with transaction.atomic(), _serialize_scheduling():
        # Capture the revision only after obtaining the scheduler lock. This
        # makes requested_at monotonic with the serialization order even when
        # two transactions arrived while no pending row existed.
        requested_at = _next_requested_at(BackgroundJob)
        available_at = requested_at
        if not immediate:
            available_at += timedelta(seconds=AMPLIFY_REDIRECT_DEBOUNCE_SECONDS)
        payload = {
            "requested_at": requested_at.isoformat(),
            "requested_redirect_ids": sorted(requested_redirect_ids),
            AMPLIFY_CONFIGURATION_PAYLOAD_KEY: _latest_known_amplify_configuration(BackgroundJob),
        }
        queued = (
            BackgroundJob.objects.select_for_update()
            .filter(
                kind=AMPLIFY_REDIRECT_JOB_KIND,
                status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY],
            )
            .order_by("created_at")
            .first()
        )
        if queued is not None:
            return _coalesce_into(queued, payload, requested_redirect_ids, available_at)

        job, _created = enqueue_job(
            kind=AMPLIFY_REDIRECT_JOB_KIND,
            dedupe_key=str(uuid.uuid4()),
            payload=payload,
            can_retry_after_claim=True,
            max_attempts=5,
            available_at=available_at,
        )
        return job


def get_amplify_redirect_sync_status() -> dict[str, Any]:
    """Return a small queryable health summary for admin/UI integrations."""

    from apps.core.models import BackgroundJob
    from apps.core.services.background_jobs import jobs_enabled

    latest = BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).order_by("-created_at").first()
    return {
        "configured": bool(_configured_app_id()),
        "jobs_enabled": jobs_enabled(),
        "job_id": str(latest.pk) if latest else None,
        "status": latest.status if latest else None,
        "last_error": latest.last_error if latest else "",
        "attempts": latest.attempts if latest else 0,
        "updated_at": latest.updated_at if latest else None,
    }
