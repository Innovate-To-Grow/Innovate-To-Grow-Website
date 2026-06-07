"""Read Bedrock usage metrics from CloudWatch (free GetMetricData reads only).

AWS publishes per-model invocation and token counters to the ``AWS/Bedrock``
CloudWatch namespace at no charge. We read those here instead of Cost Explorer
(``ce``), which bills per request and is deliberately never called anywhere in
this codebase.

The service degrades gracefully: a missing/denied IAM permission or absent AWS
credentials returns ``{"available": False, ...}`` with empty series rather than
raising into the dashboard view.
"""

from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError
from django.utils import timezone

from apps.core.services.bedrock.clients import get_cloudwatch_client
from apps.core.services.bedrock.exceptions import BedrockError

NAMESPACE = "AWS/Bedrock"
# One point per day. CloudWatch Sum over the daily period gives daily totals.
PERIOD_SECONDS = 86400

# The three counters we chart per model.
_METRICS = (
    ("InputTokenCount", "input_tokens"),
    ("OutputTokenCount", "output_tokens"),
    ("Invocations", "invocations"),
)


def _empty(reason):
    return {
        "available": False,
        "reason": reason,
        "by_model": [],
        "daily": [],
        "today": {"input_tokens": 0, "output_tokens": 0, "invocations": 0},
        "totals": {"input_tokens": 0, "output_tokens": 0, "invocations": 0},
    }


def fetch_bedrock_metrics(*, days=30):
    """Return Bedrock usage metrics for the trailing ``days`` window.

    Shape::

        {
            "available": True,
            "by_model": [{"model_id", "input_tokens", "output_tokens", "invocations"}],
            "daily": [{"date", "input_tokens", "output_tokens", "invocations"}],
            "today": {"input_tokens", "output_tokens", "invocations"},
            "totals": {"input_tokens", "output_tokens", "invocations"},
        }
    """
    try:
        client = get_cloudwatch_client()
    except BedrockError:
        # No active/configured AWS credentials.
        return _empty("unconfigured")
    except Exception:  # noqa: BLE001 -- e.g. a DB error loading credentials; never 500 the dashboard.
        return _empty("error")

    try:
        model_ids = _discover_model_ids(client)
        now = timezone.now()
        start = now - timedelta(days=days)
        results = _get_metric_data(client, model_ids, start, now)
    except (ClientError, BotoCoreError):
        # AccessDenied, throttling, network -- never surface to the view.
        return _empty("permission")
    except Exception:  # noqa: BLE001 -- defensive: a dashboard must never 500 on metrics.
        return _empty("error")

    return _build_payload(results, now)


def _discover_model_ids(client):
    """List the ModelId dimension values seen on Invocations.

    Also tolerate aggregate metrics published without a ModelId dimension by
    representing them under an empty-string id (charted as "(all models)").
    """
    model_ids = []
    has_unscoped = False
    paginator = client.get_paginator("list_metrics")
    for page in paginator.paginate(Namespace=NAMESPACE, MetricName="Invocations"):
        for metric in page.get("Metrics", []):
            dims = {d["Name"]: d["Value"] for d in metric.get("Dimensions", [])}
            model_id = dims.get("ModelId")
            if model_id is None:
                has_unscoped = True
            elif model_id not in model_ids:
                model_ids.append(model_id)
    if has_unscoped:
        model_ids.append("")
    return model_ids


def _metric_queries(model_ids):
    """Build the GetMetricData query list, one query per (model, metric)."""
    queries = []
    for model_index, model_id in enumerate(model_ids):
        dimensions = [{"Name": "ModelId", "Value": model_id}] if model_id else []
        for metric_name, key in _METRICS:
            queries.append(
                {
                    # ``mN_input_tokens`` etc. -- ids must be unique and start lower-case.
                    "Id": f"m{model_index}_{key}",
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


def _get_metric_data(client, model_ids, start, end):
    """Run GetMetricData and return raw per-query (timestamps, values) series."""
    if not model_ids:
        return {"model_ids": [], "series": {}}

    queries = _metric_queries(model_ids)
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
    return {"model_ids": model_ids, "series": series}


def _build_payload(results, now):
    """Fold the raw per-query series into by_model / daily / totals / today."""
    model_ids = results["model_ids"]
    series = results["series"]

    daily_map = {}  # ISO date string -> counters
    by_model = []
    totals = {"input_tokens": 0, "output_tokens": 0, "invocations": 0}
    today = {"input_tokens": 0, "output_tokens": 0, "invocations": 0}
    today_cutoff = now - timedelta(hours=24)

    for model_index, model_id in enumerate(model_ids):
        model_totals = {"input_tokens": 0, "output_tokens": 0, "invocations": 0}
        for _metric_name, key in _METRICS:
            entry = series.get(f"m{model_index}_{key}")
            if not entry:
                continue
            for ts, value in zip(entry["timestamps"], entry["values"], strict=False):
                amount = int(round(value))
                model_totals[key] += amount
                totals[key] += amount
                date_key = ts.date().isoformat()
                bucket = daily_map.setdefault(date_key, {"input_tokens": 0, "output_tokens": 0, "invocations": 0})
                bucket[key] += amount
                if ts >= today_cutoff:
                    today[key] += amount
        by_model.append({"model_id": model_id or "(all models)", **model_totals})

    daily = [{"date": date, **counters} for date, counters in sorted(daily_map.items())]
    by_model.sort(key=lambda row: row["input_tokens"] + row["output_tokens"], reverse=True)

    return {
        "available": True,
        "by_model": by_model,
        "daily": daily,
        "today": today,
        "totals": totals,
    }
