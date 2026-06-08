"""Read AWS SES delivery health for the admin dashboard."""

from __future__ import annotations

from datetime import timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

NAMESPACE = "AWS/SES"
PERIOD_SECONDS = 86400
DEFAULT_WINDOW_DAYS = 183

METRICS = (
    ("Send", "attempts", "Sent"),
    ("Delivery", "success", "Delivered"),
    ("Bounce", "bounces", "Bounced"),
    ("Complaint", "complaints", "Complained"),
    ("Reject", "rejected", "Rejected"),
    ("RenderingFailure", "failed", "Rendering failures"),
    ("DeliveryDelay", "delayed", "Delivery delays"),
)
ERROR_KEYS = ("bounces", "complaints", "rejected", "failed")
SUPPRESSION_REASONS = ("BOUNCE", "COMPLAINT")


def get_delivery_dashboard_data(*, days: int = DEFAULT_WINDOW_DAYS, problem_limit: int = 50) -> dict:
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
        "campaign_errors": [],
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


def fetch_suppressed_destinations(*, days: int = DEFAULT_WINDOW_DAYS, limit: int = 50, now=None):
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
        rows = []
        paginator = client.get_paginator("list_suppressed_destinations")
        for page in paginator.paginate(
            Reasons=list(SUPPRESSION_REASONS),
            StartDate=start,
            EndDate=now,
            PageSize=100,
        ):
            for item in page.get("SuppressedDestinationSummaries", []):
                rows.append(_suppressed_destination_row(item))
    except (ClientError, BotoCoreError):
        return [], _recipient_details_meta(False, "permission")
    except Exception:  # noqa: BLE001
        return [], _recipient_details_meta(False, "error")

    rows.sort(key=lambda row: row["_last_seen_sort"], reverse=True)
    rows = rows[:limit]
    for row in rows:
        row.pop("_last_seen_sort", None)
    meta = _recipient_details_meta(True, "")
    meta["count"] = len(rows)
    return rows, meta


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


def _discover_dimension_sets(client):
    discovered = []
    seen = set()
    paginator = client.get_paginator("list_metrics")
    for metric_name, _key, _label in METRICS:
        for page in paginator.paginate(Namespace=NAMESPACE, MetricName=metric_name):
            for metric in page.get("Metrics", []):
                dimensions = metric.get("Dimensions", [])
                key = tuple(sorted((dim.get("Name", ""), dim.get("Value", "")) for dim in dimensions))
                if key not in seen:
                    seen.add(key)
                    discovered.append([{"Name": name, "Value": value} for name, value in key if name and value])
    return discovered


def _get_metric_data(client, dimension_sets, start, end):
    queries = _metric_queries(dimension_sets)
    series = {}
    next_token = None
    while True:
        kwargs = {
            "MetricDataQueries": queries,
            "StartTime": start,
            "EndTime": end,
            "ScanBy": "TimestampAscending",
        }
        if next_token:
            kwargs["NextToken"] = next_token
        response = client.get_metric_data(**kwargs)
        for result in response.get("MetricDataResults", []):
            entry = series.setdefault(result["Id"], {"timestamps": [], "values": []})
            entry["timestamps"].extend(result.get("Timestamps", []))
            entry["values"].extend(result.get("Values", []))
        next_token = response.get("NextToken")
        if not next_token:
            break
    return {"dimension_sets": dimension_sets, "series": series}


def _metric_queries(dimension_sets):
    queries = []
    for dim_index, dimensions in enumerate(dimension_sets):
        for metric_name, key, _label in METRICS:
            queries.append(
                {
                    "Id": f"d{dim_index}_{key}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": NAMESPACE,
                            "MetricName": metric_name,
                            "Dimensions": dimensions,
                        },
                        "Period": PERIOD_SECONDS,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )
    return queries


def _has_values(results) -> bool:
    return any(value for entry in results["series"].values() for value in entry.get("values", []))


def _build_metric_payload(results, *, days: int, now, source: str) -> dict:
    summary = _zero_summary()
    daily_map = _empty_daily_map(days, now)

    for dim_index, _dimensions in enumerate(results["dimension_sets"]):
        for _metric_name, key, _label in METRICS:
            entry = results["series"].get(f"d{dim_index}_{key}")
            if not entry:
                continue
            for ts, value in zip(entry["timestamps"], entry["values"], strict=False):
                amount = int(round(value or 0))
                summary[key] += amount
                day = _local_day(ts).isoformat()
                if day in daily_map:
                    daily_map[day][key] += amount

    summary["problems"] = sum(summary[key] for key in ERROR_KEYS)
    if summary["attempts"] < summary["success"] + summary["problems"]:
        summary["attempts"] = summary["success"] + summary["problems"]
    summary["failure_rate"] = round((summary["problems"] / summary["attempts"]) * 100, 1) if summary["attempts"] else 0

    daily = []
    for date, counters in daily_map.items():
        daily_problems = sum(counters[key] for key in ERROR_KEYS)
        daily_attempts = counters["attempts"]
        if daily_attempts < counters["success"] + daily_problems:
            daily_attempts = counters["success"] + daily_problems
        daily.append({"date": date, "attempts": daily_attempts, "problems": daily_problems})

    return {
        "summary": summary,
        "daily": daily,
        "status_breakdown": _status_breakdown(summary),
        "metrics": {
            "available": True,
            "reason": "",
            "source": source,
            "namespace": NAMESPACE,
            "dimension_count": len(results["dimension_sets"]),
        },
    }


def _empty_metric_payload(*, days: int, now, reason: str) -> dict:
    payload = _build_metric_payload(
        {"dimension_sets": [[]], "series": {}},
        days=days,
        now=now,
        source="CloudWatch account SES metrics",
    )
    payload["metrics"].update({"available": False, "reason": reason})
    return payload


def _zero_summary() -> dict:
    return {
        "attempts": 0,
        "success": 0,
        "problems": 0,
        "failure_rate": 0,
        "campaign_attempts": 0,
        "campaign_errors": 0,
        "ticket_sent": 0,
        "ticket_errors": 0,
        "pending": 0,
        "bounces": 0,
        "complaints": 0,
        "rejected": 0,
        "failed": 0,
        "delayed": 0,
    }


def _empty_daily_map(days: int, now):
    today = timezone.localdate(now)
    return {
        (today - timedelta(days=offset)).isoformat(): {key: 0 for _metric_name, key, _label in METRICS}
        for offset in range(days - 1, -1, -1)
    }


def _status_breakdown(summary: dict) -> list[dict]:
    mapping = (
        ("bounces", "bounced", "Bounced"),
        ("complaints", "complained", "Complained"),
        ("rejected", "rejected", "Rejected"),
        ("failed", "failed", "Rendering failures"),
        ("delayed", "delayed", "Delivery delays"),
        ("success", "delivered", "Delivered"),
        ("attempts", "sent", "Sent"),
    )
    return [
        {"status": status, "label": label, "count": summary[key]} for key, status, label in mapping if summary.get(key)
    ]


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


def _recipient_details_meta(available: bool, reason: str) -> dict:
    return {
        "available": available,
        "reason": reason,
        "source": "AWS SES account suppression list",
        "count": 0,
    }


def _aws_meta(metric_payload: dict, recipient_details: dict) -> dict:
    email_config = EmailServiceConfig.load()
    aws_config = AWSCredentialConfig.load()
    configured = bool(email_config.ses_from_email and aws_config.ses_configured)
    return {
        "configured": configured,
        "email_config": email_config.name,
        "aws_config": aws_config.name,
        "region": aws_config.region,
        "source_address": email_config.source_address,
        "send_rate": email_config.ses_max_send_rate,
        "iam_key": f"...{aws_config.access_key_id[-4:]}" if aws_config.access_key_id else "Not configured",
        "metrics_available": metric_payload["metrics"]["available"],
        "metrics_reason": metric_payload["metrics"]["reason"],
        "metrics_source": metric_payload["metrics"]["source"],
        "recipient_details_available": recipient_details["available"],
        "recipient_details_reason": recipient_details["reason"],
    }


def _local_day(value):
    return timezone.localtime(value).date()


def _display_dt(value) -> str:
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%b %d, %H:%M")
