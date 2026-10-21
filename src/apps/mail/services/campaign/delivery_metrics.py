"""AWS SES CloudWatch counters: the metric queries, dimension discovery, and the dashboard payload built from them."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

NAMESPACE = "AWS/SES"


PERIOD_SECONDS = 86400


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


def _listed_dimension_keys(paginator):
    """Every SES metric's dimensions, as sorted ``(name, value)`` tuples."""
    for metric_name, _key, _label in METRICS:
        for page in paginator.paginate(Namespace=NAMESPACE, MetricName=metric_name):
            for metric in page.get("Metrics", []):
                dimensions = metric.get("Dimensions", [])
                yield tuple(sorted((dim.get("Name", ""), dim.get("Value", "")) for dim in dimensions))


def _discover_dimension_sets(client):
    discovered = []
    seen = set()
    for key in _listed_dimension_keys(client.get_paginator("list_metrics")):
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


def _datapoints(results):
    """Every returned ``(metric key, timestamp, value)``, across all dimension sets."""
    for dim_index, _dimensions in enumerate(results["dimension_sets"]):
        for _metric_name, key, _label in METRICS:
            entry = results["series"].get(f"d{dim_index}_{key}") or {"timestamps": [], "values": []}
            for ts, value in zip(entry["timestamps"], entry["values"], strict=False):
                yield key, ts, value


def _add_series(results, summary: dict, daily_map: dict) -> None:
    """Add every returned datapoint to the window totals and to its local day."""
    for key, ts, value in _datapoints(results):
        amount = int(round(value or 0))
        summary[key] += amount
        day = _local_day(ts).isoformat()
        if day in daily_map:
            daily_map[day][key] += amount


def _daily_rows(daily_map: dict) -> list[dict]:
    daily = []
    for date, counters in daily_map.items():
        daily_problems = sum(counters[key] for key in ERROR_KEYS)
        # As for the window summary: a day's attempts are never fewer than its outcomes.
        daily_attempts = max(counters["attempts"], counters["success"] + daily_problems)
        daily.append({"date": date, "attempts": daily_attempts, "problems": daily_problems})
    return daily


def _build_metric_payload(results, *, days: int, now, source: str) -> dict:
    summary = _zero_summary()
    daily_map = _empty_daily_map(days, now)
    _add_series(results, summary, daily_map)

    summary["problems"] = sum(summary[key] for key in ERROR_KEYS)
    if summary["attempts"] < summary["success"] + summary["problems"]:
        summary["attempts"] = summary["success"] + summary["problems"]
    summary["failure_rate"] = round((summary["problems"] / summary["attempts"]) * 100, 1) if summary["attempts"] else 0

    return {
        "summary": summary,
        "daily": _daily_rows(daily_map),
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


def _local_day(value):
    return timezone.localtime(value).date()
