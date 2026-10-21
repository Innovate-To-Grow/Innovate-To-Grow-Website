"""Make Amplify's custom rules match the redirect table (the provider call itself)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
)
from django.db import connection, transaction

from .config import _resolved_amplify_configuration
from .rules import canonical_amplify_base_rules, merge_amplify_rules

_AMPLIFY_RECONCILE_LOCK_ID = 0x4932475245444952  # "I2GREDIR", within signed bigint range.
_AMPLIFY_SCHEDULE_LOCK_ID = 0x4932475343484544  # "I2GSCHED", within signed bigint range.
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


@dataclass(frozen=True)
class AmplifyReconcileResult:
    changed: bool
    active_redirect_count: int
    managed_rule_count: int
    total_rule_count: int


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
