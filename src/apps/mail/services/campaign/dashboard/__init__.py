"""Read AWS SES delivery health for the admin dashboard."""

from __future__ import annotations

import logging
from datetime import timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.utils import timezone

from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

from .delivery_metrics import (
    _build_metric_payload,
    _discover_dimension_sets,
    _empty_metric_payload,
    _get_metric_data,
    _has_values,
)
from .meta import (
    DEFAULT_WINDOW_DAYS,
    PERMISSION_ERROR_CODES,
    _aws_meta,
    _client_error_code,
    _client_error_reason,
    _display_dt,
    _list_suppressed_rows,
    _preferred_dimension_groups,
    _recipient_details_meta,
    _recipient_reason_counts,
)
from .meta import PUBLIC_ERROR_MESSAGES as PUBLIC_ERROR_MESSAGES

RECIPIENT_DETAIL_ACTIONS = ("ses:ListSuppressedDestinations", "ses:GetSuppressedDestination")
_PUBLIC_ERROR_CODES = {code: code for code in PERMISSION_ERROR_CODES}

logger = logging.getLogger(__name__)


def get_delivery_dashboard_data(*, days: int = DEFAULT_WINDOW_DAYS, problem_limit: int | None = None) -> dict:
    """Return AWS-backed SES dashboard metrics.

    Delivery counts come from CloudWatch ``AWS/SES`` metrics. Recipient-level
    failure rows come from the AWS SES account suppression list because
    CloudWatch metrics are aggregate counters and do not include email
    addresses. No local delivery log tables are used for dashboard data.
    """

    now = timezone.now()
    metric_payload = fetch_ses_cloudwatch_metrics(days=days, now=now)
    problem_rows, recipient_details = fetch_suppressed_destinations(days=days, limit=problem_limit, now=now)

    return {
        "window_days": days,
        "generated_at": now.isoformat(),
        "summary": metric_payload["summary"],
        "aws": _aws_meta(metric_payload, recipient_details),
        "metrics": metric_payload["metrics"],
        "recipient_details": recipient_details,
        "daily": metric_payload["daily"],
        "status_breakdown": metric_payload["status_breakdown"],
        "problem_recipients": problem_rows,
    }


def fetch_ses_cloudwatch_metrics(*, days: int = DEFAULT_WINDOW_DAYS, now=None) -> dict:
    """Read AWS SES CloudWatch counters for the trailing window."""

    now = now or timezone.now()
    try:
        client = _cloudwatch_client()
    except AwsCredentialsError:
        return _empty_metric_payload(days=days, now=now, reason="unconfigured")
    except Exception:  # noqa: BLE001 -- dashboard data must never 500 on config lookup failures.
        return _empty_metric_payload(days=days, now=now, reason="error")

    start = now - timedelta(days=days)
    dimension_groups = _preferred_dimension_groups()

    try:
        for source, dimension_sets in dimension_groups:
            results = _get_metric_data(client, dimension_sets, start, now)
            if _has_values(results):
                return _build_metric_payload(results, days=days, now=now, source=source)

        discovered = _discover_dimension_sets(client)
        if discovered:
            results = _get_metric_data(client, discovered, start, now)
            return _build_metric_payload(results, days=days, now=now, source="CloudWatch discovered SES metrics")
    except (ClientError, BotoCoreError):
        return _empty_metric_payload(days=days, now=now, reason="permission")
    except Exception:  # noqa: BLE001 -- defensive: show an unavailable state instead of crashing admin.
        return _empty_metric_payload(days=days, now=now, reason="error")

    return _build_metric_payload(
        {"dimension_sets": [[]], "series": {}},
        days=days,
        now=now,
        source="CloudWatch account SES metrics",
    )


def _suppression_error_meta(exc: Exception) -> dict:
    """The unavailable-state metadata for a failed suppression-list read (details go to the log only)."""
    if isinstance(exc, ClientError):
        logger.warning("Reading the SES suppression list failed: %s", exc)
        reason = _client_error_reason(exc)
        error_code = _PUBLIC_ERROR_CODES.get(_client_error_code(exc), "AwsError")
    elif isinstance(exc, BotoCoreError):
        logger.warning("Reading the SES suppression list failed: %s", exc)
        reason, error_code = "aws_error", "AwsError"
    else:
        logger.exception("Unexpected error reading the SES suppression list")
        reason, error_code = "error", "InternalError"
    return _recipient_details_meta(False, reason, error_code=error_code, required_actions=RECIPIENT_DETAIL_ACTIONS)


def fetch_suppressed_destinations(*, days: int = DEFAULT_WINDOW_DAYS, limit: int | None = None, now=None):
    """Return AWS SES account-level suppressed recipients.

    The SES suppression list is the only AWS API here that exposes recipient
    email addresses without reading local application logs. It mainly captures
    bounce and complaint addresses, not every transient send failure.
    """

    now = now or timezone.now()
    start = now - timedelta(days=days)
    try:
        client = _sesv2_client()
    except AwsCredentialsError:
        return [], _recipient_details_meta(False, "unconfigured")
    except Exception:  # noqa: BLE001
        return [], _recipient_details_meta(False, "error")

    try:
        rows = _list_suppressed_rows(client, start, now)
    except Exception as exc:  # noqa: BLE001 - every failure becomes an unavailable state.
        return [], _suppression_error_meta(exc)

    rows.sort(key=lambda row: row["_last_seen_sort"], reverse=True)
    total_count = len(rows)
    reason_counts = _recipient_reason_counts(rows)
    latest_seen = _display_dt(rows[0]["_last_seen_sort"]) if rows else "-"
    limited_rows = rows if limit is None else rows[: max(limit, 0)]
    for row in limited_rows:
        row.pop("_last_seen_sort", None)

    meta = _recipient_details_meta(True, "")
    meta.update(
        {
            "count": len(limited_rows),
            "returned_count": len(limited_rows),
            "total_count": total_count,
            "truncated": len(limited_rows) < total_count,
            "limit": limit,
            "reason_counts": reason_counts,
            "latest_seen": latest_seen,
            "window_days": days,
        }
    )
    return limited_rows, meta


def _cloudwatch_client():
    creds = resolve_aws_credentials("ses")
    return boto3.client(
        "cloudwatch",
        region_name=creds.region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
    )


def _sesv2_client():
    creds = resolve_aws_credentials("ses")
    return boto3.client(
        "sesv2",
        region_name=creds.region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
    )
