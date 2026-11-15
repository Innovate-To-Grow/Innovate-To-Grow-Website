"""The CloudWatch GetMetricData queries for Bedrock: which models report, and their daily invocation and token
series."""

NAMESPACE = "AWS/Bedrock"
# One point per day. CloudWatch Sum over the daily period gives daily totals.
PERIOD_SECONDS = 86400

# The three counters we chart per model.
_METRICS = (
    ("InputTokenCount", "input_tokens"),
    ("OutputTokenCount", "output_tokens"),
    ("Invocations", "invocations"),
)


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
