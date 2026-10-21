"""Read AWS SES delivery health for the admin dashboard."""

from __future__ import annotations

import logging
from datetime import timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

from .delivery_metrics import (
    _build_metric_payload,
    _discover_dimension_sets,
    _empty_metric_payload,
    _get_metric_data,
    _has_values,
)

DEFAULT_WINDOW_DAYS = 183

SUPPRESSION_REASONS = ("BOUNCE", "COMPLAINT")
RECIPIENT_DETAIL_ACTIONS = ("ses:ListSuppressedDestinations", "ses:GetSuppressedDestination")
PERMISSION_ERROR_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "AuthorizationError",
    "InvalidClientTokenId",
    "SignatureDoesNotMatch",
    "UnauthorizedOperation",
    "UnrecognizedClientException",
}
# Exception details never reach the JSON payload: the dashboard only sees these
# fixed messages (keyed by reason) plus an allowlisted error code, while the
# full exception text goes to the server log.
PUBLIC_ERROR_MESSAGES = {
    "permission": "The configured AWS credentials are missing the required SES suppression-list permissions.",
    "aws_error": "AWS returned an error while reading the SES suppression list.",
    "error": "An unexpected error occurred while reading the SES suppression list.",
}
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


def _list_suppressed_rows(client, start, end) -> list[dict]:
    rows = []
    kwargs = {
        "Reasons": list(SUPPRESSION_REASONS),
        "StartDate": start,
        "EndDate": end,
        "PageSize": 100,
    }
    while True:
        page = client.list_suppressed_destinations(**kwargs)
        rows.extend(_suppressed_destination_row(item) for item in page.get("SuppressedDestinationSummaries", []))
        next_token = page.get("NextToken")
        if not next_token:
            return rows
        kwargs["NextToken"] = next_token


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


def _preferred_dimension_groups():
    groups = [("CloudWatch account SES metrics", [[]])]
    configuration_set = _configuration_set_name()
    if configuration_set:
        groups.append(
            (
                f"CloudWatch SES configuration set: {configuration_set}",
                [[{"Name": "ConfigurationSet", "Value": configuration_set}]],
            )
        )
    return groups


def _configuration_set_name() -> str:
    return (getattr(settings, "SES_CONFIGURATION_SET_NAME", "") or "").strip()


def _suppressed_destination_row(item: dict) -> dict:
    reason = item.get("Reason", "")
    email = item.get("EmailAddress", "")
    last_seen = item.get("LastUpdateTime")
    status = "bounced" if reason == "BOUNCE" else "complained" if reason == "COMPLAINT" else "failed"
    label = "Bounced" if reason == "BOUNCE" else "Complained" if reason == "COMPLAINT" else reason.title()
    return {
        "email": email,
        "name": "",
        "source": "AWS SES Suppression List",
        "context": "Account-level suppression",
        "status": status,
        "label": label,
        "reason": reason or "Suppressed by SES",
        "last_seen": _display_dt(last_seen),
        "count": 1,
        "_last_seen_sort": last_seen or timezone.now() - timedelta(days=36500),
    }


def _recipient_reason_counts(rows: list[dict]) -> dict:
    counts = dict.fromkeys(SUPPRESSION_REASONS, 0)
    for row in rows:
        reason = row.get("reason")
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _recipient_details_meta(
    available: bool,
    reason: str,
    *,
    error_code: str = "",
    required_actions: tuple[str, ...] = (),
) -> dict:
    return {
        "available": available,
        "reason": reason,
        "source": "AWS SES account suppression list",
        "count": 0,
        "error_code": error_code,
        "error_message": PUBLIC_ERROR_MESSAGES.get(reason, ""),
        "required_actions": list(required_actions),
        "returned_count": 0,
        "total_count": 0,
        "truncated": False,
        "limit": None,
        "reason_counts": {},
        "latest_seen": "-",
        "window_days": DEFAULT_WINDOW_DAYS,
    }


def _aws_meta(metric_payload: dict, recipient_details: dict) -> dict:
    email_config = EmailServiceConfig.load()
    aws_config = AWSCredentialConfig.load()
    configured = email_config.ses_configured
    return {
        "configured": configured,
        "email_config": email_config.name,
        "aws_config": aws_config.name,
        "region": aws_config.region,
        "source_address": email_config.source_address,
        "send_rate": email_config.max_send_rate,
        "iam_key": f"...{aws_config.access_key_id[-4:]}" if aws_config.access_key_id else "Not configured",
        "metrics_available": metric_payload["metrics"]["available"],
        "metrics_reason": metric_payload["metrics"]["reason"],
        "metrics_source": metric_payload["metrics"]["source"],
        "recipient_details_available": recipient_details["available"],
        "recipient_details_reason": recipient_details["reason"],
        "recipient_details_error_code": recipient_details.get("error_code", ""),
        "recipient_details_error_message": recipient_details.get("error_message", ""),
        "recipient_details_required_actions": recipient_details.get("required_actions", []),
    }


def _display_dt(value) -> str:
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%b %d, %H:%M")


def _client_error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "")


def _client_error_reason(exc: ClientError) -> str:
    code = _client_error_code(exc)
    return "permission" if code in PERMISSION_ERROR_CODES or "denied" in code.lower() else "aws_error"
