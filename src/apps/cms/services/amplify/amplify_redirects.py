"""Reconcile backend-owned routing into AWS Amplify custom rules.

Deployment settings define canonical passthrough/fallback rules and the database
defines CMS redirects. Each run preserves unrelated Amplify rules.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
)
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

AMPLIFY_REDIRECT_JOB_KIND = "cms.amplify_redirects"
AMPLIFY_REDIRECT_DEBOUNCE_SECONDS = 2
AMPLIFY_CONFIGURATION_PAYLOAD_KEY = "amplify_configuration"
_AMPLIFY_RECONCILE_LOCK_ID = 0x4932475245444952  # "I2GREDIR", within signed bigint range.
_AMPLIFY_SCHEDULE_LOCK_ID = 0x4932475343484544  # "I2GSCHED", within signed bigint range.
_AMPLIFY_SPA_SOURCE = (
    r"</^[^.]+$|\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|webp|avif|"
    r"woff|woff2|ttf|otf|eot|map|json|xml|webmanifest)$)([^.]+$)/>"
)
_AMPLIFY_BASE_RULE_SOURCES = {
    "/sitemap.xml",
    "/api/<*>",
    "/admin",
    "/admin/<*>",
    "/static/<*>",
    "/media/<*>",
}
_AMPLIFY_LEGACY_SPA_SOURCES = {
    "/<*>",
    "/*",
    r"</^[^.]+$/>",
}
_TRANSIENT_AMPLIFY_ERROR_CODES = {
    "InternalFailure",
    "InternalServerError",
    "InternalServerException",
    "LimitExceededException",
    "PriorRequestNotComplete",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
    "ServiceUnavailableException",
    "Throttling",
    "ThrottlingException",
    "TooManyRequestsException",
}


class AmplifyRedirectSyncError(RuntimeError):
    """Base error for edge redirect reconciliation."""


class AmplifyRedirectConfigurationError(AmplifyRedirectSyncError):
    """The deployment has not provided enough configuration to sync."""


@dataclass(frozen=True)
class AmplifyReconcileResult:
    changed: bool
    active_redirect_count: int
    managed_rule_count: int
    total_rule_count: int


def _configured_app_id() -> str:
    return str(getattr(settings, "AMPLIFY_APP_ID", "") or "").strip()


def _configured_region() -> str:
    return str(
        getattr(settings, "AWS_REGION", "") or getattr(settings, "AWS_S3_REGION_NAME", "") or "us-west-2"
    ).strip()


def _configured_proxy_admin_paths() -> bool:
    value = getattr(settings, "AMPLIFY_PROXY_ADMIN_PATHS", False)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_amplify_configuration() -> dict[str, Any]:
    """Capture the provider/base-rule settings that one queued revision owns.

    Jobs carry this snapshot so any compatible worker can execute them during
    an ECS rolling deployment without substituting that worker's older
    environment values.
    """

    return {
        "config_revision": str(getattr(settings, "AMPLIFY_CONFIG_REVISION", "0") or "0").strip() or "0",
        "app_id": _configured_app_id(),
        "region": _configured_region(),
        "backend_proxy_url": str(getattr(settings, "AMPLIFY_BACKEND_PROXY_URL", "") or "").strip().rstrip("/"),
        "proxy_admin_paths": _configured_proxy_admin_paths(),
    }


def _configuration_revision_key(configuration: dict[str, Any] | None) -> tuple[int, ...]:
    """Return a numerically comparable deployment generation.

    Production injects ``github.run_id.github.run_attempt``. Missing or
    malformed values are treated as generation zero for compatibility with
    jobs queued before this field existed.
    """

    if not isinstance(configuration, dict):
        return (0,)
    value = str(configuration.get("config_revision") or "0").strip()
    components = value.split(".")
    if not components or any(not component.isdigit() for component in components):
        return (0,)
    return tuple(int(component) for component in components)


def _latest_known_amplify_configuration(background_job_model) -> dict[str, Any]:
    """Keep an older rolling task from replacing a newer shared config.

    Amplify jobs are durable and retained, so their snapshots also form the
    shared generation ledger. The scheduler lock serializes selection and
    update of this ledger. A route edit produced by an older web task still
    queues a reconciliation, but carries forward the newest known snapshot.
    """

    configured = _configured_amplify_configuration()
    selected = configured
    selected_key = _configuration_revision_key(configured)
    payloads = (
        background_job_model.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND)
        .order_by("-created_at")
        .values_list("payload", flat=True)
    )
    for payload in payloads:
        candidate = (payload or {}).get(AMPLIFY_CONFIGURATION_PAYLOAD_KEY)
        candidate_key = _configuration_revision_key(candidate)
        if isinstance(candidate, dict) and candidate_key > selected_key:
            selected = dict(candidate)
            selected_key = candidate_key
    return selected


def _resolved_amplify_configuration(configuration: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _configured_amplify_configuration() if configuration is None else configuration
    if not isinstance(raw, dict):
        raise AmplifyRedirectConfigurationError("Amplify reconciliation configuration is invalid.")

    app_id = str(raw.get("app_id") or "").strip()
    if not app_id:
        raise AmplifyRedirectConfigurationError("AMPLIFY_APP_ID is not configured.")

    region = str(raw.get("region") or "us-west-2").strip() or "us-west-2"
    backend_proxy_url = str(raw.get("backend_proxy_url") or "").strip().rstrip("/")
    parsed = urlsplit(backend_proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise AmplifyRedirectConfigurationError(
            "AMPLIFY_BACKEND_PROXY_URL must be an absolute HTTP(S) URL without query or fragment."
        )

    proxy_admin_paths = raw.get("proxy_admin_paths", False)
    if not isinstance(proxy_admin_paths, bool):
        proxy_admin_paths = str(proxy_admin_paths or "").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "app_id": app_id,
        "region": region,
        "backend_proxy_url": backend_proxy_url,
        "proxy_admin_paths": proxy_admin_paths,
    }


def _canonical_path(path: str) -> str:
    value = str(path or "").strip()
    if not value.startswith("/"):
        raise AmplifyRedirectSyncError("Amplify redirect paths must start with '/'.")
    return "/" if value == "/" else value.rstrip("/")


def amplify_source_variants(source_path: str) -> tuple[str, ...]:
    """Return exact canonical and trailing-slash variants for one source."""

    canonical = _canonical_path(source_path)
    if canonical == "/":
        return (canonical,)
    return canonical, f"{canonical}/"


def _managed_rules(redirects: list[dict[str, Any]]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for redirect in sorted(redirects, key=lambda row: (row["source_path"], row["destination_path"])):
        target = _canonical_path(redirect["destination_path"])
        for source in amplify_source_variants(redirect["source_path"]):
            if source in seen_sources:
                continue
            seen_sources.add(source)
            rules.append({"source": source, "target": target, "status": "301"})
    return rules


def canonical_amplify_base_rules(
    *,
    backend_proxy_url: str,
    proxy_admin_paths: bool,
) -> list[dict[str, str]]:
    """Return the backend-owned passthrough rules and final SPA fallback."""

    backend_proxy_url = backend_proxy_url.rstrip("/")
    rules = [
        {
            "source": "/sitemap.xml",
            "target": f"{backend_proxy_url}/sitemap.xml",
            "status": "200",
        },
        {
            "source": "/api/<*>",
            "target": f"{backend_proxy_url}/<*>",
            "status": "200",
        },
    ]
    if proxy_admin_paths:
        rules.extend(
            [
                {
                    "source": "/admin",
                    "target": f"{backend_proxy_url}/admin/",
                    "status": "200",
                },
                {
                    "source": "/admin/<*>",
                    "target": f"{backend_proxy_url}/admin/<*>",
                    "status": "200",
                },
                {
                    "source": "/static/<*>",
                    "target": f"{backend_proxy_url}/static/<*>",
                    "status": "200",
                },
                {
                    "source": "/media/<*>",
                    "target": f"{backend_proxy_url}/media/<*>",
                    "status": "200",
                },
            ]
        )
    rules.append(
        {
            "source": _AMPLIFY_SPA_SOURCE,
            "target": "/index.html",
            "status": "200",
        }
    )
    return rules


def _is_spa_fallback(rule: dict[str, Any]) -> bool:
    if not _targets_spa_index(rule):
        return False
    status = str(rule.get("status") or "").upper()
    source = str(rule.get("source") or "").strip()
    is_catch_all = source == _AMPLIFY_SPA_SOURCE or source in _AMPLIFY_LEGACY_SPA_SOURCES
    return is_catch_all and status in {"200", "404-200"}


def _targets_spa_index(rule: dict[str, Any]) -> bool:
    target = str(rule.get("target") or "").split("?", 1)[0].rstrip("/")
    return target in {"index.html", "/index.html"}


def _owns_edge_source(redirect: dict[str, Any]) -> bool:
    """Whether this row may replace or remove an existing edge rule."""

    return bool(redirect.get("is_active") or redirect.get("edge_rule_managed"))


def merge_amplify_rules(
    *,
    existing_rules: list[dict[str, Any]],
    all_redirects: list[dict[str, Any]],
    base_rules: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Build the desired rule list while preserving unrelated rule order."""

    owned_sources = {
        source
        for redirect in all_redirects
        if _owns_edge_source(redirect)
        for source in amplify_source_variants(redirect["source_path"])
    }
    active_redirects = [redirect for redirect in all_redirects if redirect["is_active"]]
    managed_rules = _managed_rules(active_redirects)
    if base_rules is not None:
        base_rules = [dict(rule) for rule in base_rules]
        base_fallbacks = [rule for rule in base_rules if _is_spa_fallback(rule)]
        if len(base_fallbacks) != 1:
            raise AmplifyRedirectSyncError("Canonical Amplify rules must contain exactly one SPA fallback.")
        base_passthroughs = [rule for rule in base_rules if not _is_spa_fallback(rule)]
        # All reserved passthrough sources belong to this reconciler, including
        # the optional admin rules when they are disabled. This lets a config
        # change remove the previously managed admin proxies deterministically.
        owned_sources.update(_AMPLIFY_BASE_RULE_SOURCES)
        unmanaged_rules = [
            dict(rule)
            for rule in existing_rules
            if str(rule.get("source") or "") not in owned_sources and not _is_spa_fallback(rule)
        ]
        # Exact CMS redirects must precede every preserved wildcard/regex
        # rule that could otherwise shadow them. Reserved base passthroughs
        # cannot collide because those paths are rejected as redirect sources.
        desired_rules = [*base_passthroughs, *managed_rules, *unmanaged_rules, *base_fallbacks]
        return desired_rules, len(active_redirects), len(managed_rules)

    unmanaged_rules = [dict(rule) for rule in existing_rules if str(rule.get("source") or "") not in owned_sources]

    fallback_index = next(
        (index for index, rule in enumerate(unmanaged_rules) if _is_spa_fallback(rule)),
        len(unmanaged_rules),
    )
    desired_rules = [
        *unmanaged_rules[:fallback_index],
        *managed_rules,
        *unmanaged_rules[fallback_index:],
    ]
    return desired_rules, len(active_redirects), len(managed_rules)


@contextmanager
def _serialize_reconciliations():
    """Serialize workers with a transaction-scoped PostgreSQL advisory lock."""

    if connection.vendor != "postgresql":
        yield
        return

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_AMPLIFY_RECONCILE_LOCK_ID])
        yield


@contextmanager
def _serialize_scheduling():
    """Serialize scheduler revisions inside the caller's database transaction."""

    if connection.vendor != "postgresql":
        yield
        return

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_AMPLIFY_SCHEDULE_LOCK_ID])
    yield


def reconcile_amplify_redirects(
    *,
    client=None,
    configuration: dict[str, Any] | None = None,
) -> AmplifyReconcileResult:
    """Make Amplify custom rules exactly reflect the current redirect table."""

    resolved_configuration = _resolved_amplify_configuration(configuration)
    app_id = resolved_configuration["app_id"]

    from apps.cms.models import RouteRedirect

    with _serialize_reconciliations():
        base_rules = canonical_amplify_base_rules(
            backend_proxy_url=resolved_configuration["backend_proxy_url"],
            proxy_admin_paths=resolved_configuration["proxy_admin_paths"],
        )
        all_redirects = list(
            RouteRedirect.objects.order_by("source_path").values(
                "id",
                "source_path",
                "destination_path",
                "is_active",
                "edge_rule_managed",
            )
        )
        amplify = client or boto3.client("amplify", region_name=resolved_configuration["region"])
        response = amplify.get_app(appId=app_id)
        existing_rules = [dict(rule) for rule in response.get("app", {}).get("customRules") or []]
        desired_rules, active_count, managed_count = merge_amplify_rules(
            existing_rules=existing_rules,
            all_redirects=all_redirects,
            base_rules=base_rules,
        )

        changed = desired_rules != existing_rules
        if changed:
            amplify.update_app(appId=app_id, customRules=desired_rules)

        # A successful reconciliation confirms ownership of every active
        # source, including rules already identical at GetApp time and rules
        # applied by an earlier UpdateApp whose response was lost. Once an
        # administrator activates the DB mapping, later deactivation must be
        # able to remove that source deterministically.
        active_ids = [redirect["id"] for redirect in all_redirects if redirect["is_active"]]
        cleanup_ids = [
            redirect["id"] for redirect in all_redirects if not redirect["is_active"] and redirect["edge_rule_managed"]
        ]
        if active_ids:
            RouteRedirect.objects.filter(pk__in=active_ids).update(edge_rule_managed=True)
        if cleanup_ids:
            # Keep ownership if the row was reactivated while the provider
            # call was in flight; otherwise cleanup is now confirmed.
            RouteRedirect.objects.filter(pk__in=cleanup_ids, is_active=False).update(edge_rule_managed=False)

    return AmplifyReconcileResult(
        changed=changed,
        active_redirect_count=active_count,
        managed_rule_count=managed_count,
        total_rule_count=len(desired_rules),
    )


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


def _is_transient_amplify_error(exc: BaseException) -> bool:
    if isinstance(exc, ClientError):
        response = exc.response or {}
        code = str(response.get("Error", {}).get("Code") or "")
        http_status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in _TRANSIENT_AMPLIFY_ERROR_CODES or (
            isinstance(http_status, int) and (http_status in {408, 429} or http_status >= 500)
        )
    if isinstance(exc, NoCredentialsError | PartialCredentialsError | ParamValidationError):
        return False
    return isinstance(exc, BotoCoreError | TimeoutError | ConnectionError)


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
            reconcile_amplify_redirects(configuration=payload.get(AMPLIFY_CONFIGURATION_PAYLOAD_KEY))
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
            requested_redirect_ids.update((queued.payload or {}).get("requested_redirect_ids") or [])
            payload["requested_redirect_ids"] = sorted(requested_redirect_ids)
            queued.status = BackgroundJob.Status.PENDING
            queued.payload = payload
            queued.available_at = available_at
            queued.attempts = 0
            queued.completed_at = None
            queued.last_error = ""
            queued.save(
                update_fields=[
                    "status",
                    "payload",
                    "available_at",
                    "attempts",
                    "completed_at",
                    "last_error",
                    "updated_at",
                ]
            )
            return queued

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
