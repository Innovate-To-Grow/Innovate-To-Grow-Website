"""Tests for the assistant usage-stats services (CloudWatch mocked).

Cost Explorer (``ce``) is forbidden: several tests assert ``boto3.client`` is
never called with ``"ce"`` anywhere in the flow.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from apps.system_intelligence.services.bedrock.exceptions import BedrockError
from apps.system_intelligence.services.usage_stats import (
    fetch_bedrock_metrics,
)

CLOUDWATCH_PATH = "apps.system_intelligence.services.usage_stats.cloudwatch"


def _ts(day):
    return datetime(2026, 6, day, 12, 0, tzinfo=UTC)


def _now(day):
    # An hour after the data points, so the trailing-24h "today" window excludes
    # the same-clock-time point from the previous day (cutoff = now - 24h).
    return datetime(2026, 6, day, 13, 0, tzinfo=UTC)


def _make_cloudwatch_client():
    """A MagicMock CloudWatch client returning two days of data for one model."""
    client = MagicMock()

    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Metrics": [{"Dimensions": [{"Name": "ModelId", "Value": "anthropic.claude"}]}]}
    ]
    client.get_paginator.return_value = paginator

    # One query per (model, metric): m0_input_tokens / m0_output_tokens / m0_invocations.
    client.get_metric_data.return_value = {
        "MetricDataResults": [
            {"Id": "m0_input_tokens", "Timestamps": [_ts(5), _ts(6)], "Values": [100.0, 200.0]},
            {"Id": "m0_output_tokens", "Timestamps": [_ts(5), _ts(6)], "Values": [10.0, 20.0]},
            {"Id": "m0_invocations", "Timestamps": [_ts(5), _ts(6)], "Values": [1.0, 2.0]},
        ]
    }
    return client


class FetchBedrockMetricsTest(TestCase):
    def test_happy_path_builds_series_and_totals(self):
        client = _make_cloudwatch_client()
        # Freeze "now" so the 24h "today" window is deterministic.
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", return_value=client):
            with patch(f"{CLOUDWATCH_PATH}.timezone.now", return_value=_now(6)):
                result = fetch_bedrock_metrics(days=30)

        self.assertTrue(result["available"])
        # by_model rolls up both days for the single model.
        self.assertEqual(len(result["by_model"]), 1)
        model = result["by_model"][0]
        self.assertEqual(model["model_id"], "anthropic.claude")
        self.assertEqual(model["input_tokens"], 300)
        self.assertEqual(model["output_tokens"], 30)
        self.assertEqual(model["invocations"], 3)
        # totals match the single model here.
        self.assertEqual(result["totals"], {"input_tokens": 300, "output_tokens": 30, "invocations": 3})
        # daily has two dated buckets, ISO date strings, ascending.
        self.assertEqual([d["date"] for d in result["daily"]], ["2026-06-05", "2026-06-06"])
        self.assertEqual(result["daily"][0]["input_tokens"], 100)
        # "today" = last 24h from frozen now (_ts(6)); only the day-6 point qualifies.
        self.assertEqual(result["today"], {"input_tokens": 200, "output_tokens": 20, "invocations": 2})

    def test_tolerates_metric_without_model_id(self):
        client = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Metrics": [{"Dimensions": []}]}]
        client.get_paginator.return_value = paginator
        client.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "m0_input_tokens", "Timestamps": [_ts(6)], "Values": [42.0]},
                {"Id": "m0_output_tokens", "Timestamps": [_ts(6)], "Values": [4.0]},
                {"Id": "m0_invocations", "Timestamps": [_ts(6)], "Values": [1.0]},
            ]
        }
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", return_value=client):
            with patch(f"{CLOUDWATCH_PATH}.timezone.now", return_value=_now(6)):
                result = fetch_bedrock_metrics()

        self.assertTrue(result["available"])
        # Unscoped metric is labelled "(all models)".
        self.assertEqual(result["by_model"][0]["model_id"], "(all models)")
        self.assertEqual(result["totals"]["input_tokens"], 42)
        # The query dimensions list must be empty for the unscoped model.
        sent = client.get_metric_data.call_args.kwargs["MetricDataQueries"]
        self.assertEqual(sent[0]["MetricStat"]["Metric"]["Dimensions"], [])

    def test_paginates_get_metric_data_next_token(self):
        client = _make_cloudwatch_client()
        client.get_metric_data.side_effect = [
            {
                "MetricDataResults": [
                    {"Id": "m0_input_tokens", "Timestamps": [_ts(5)], "Values": [100.0]},
                ],
                "NextToken": "more",
            },
            {
                "MetricDataResults": [
                    {"Id": "m0_input_tokens", "Timestamps": [_ts(6)], "Values": [50.0]},
                ]
            },
        ]
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", return_value=client):
            with patch(f"{CLOUDWATCH_PATH}.timezone.now", return_value=_ts(6)):
                result = fetch_bedrock_metrics()
        self.assertEqual(result["totals"]["input_tokens"], 150)
        self.assertEqual(client.get_metric_data.call_count, 2)

    def test_no_models_returns_empty_series_but_available(self):
        client = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Metrics": []}]
        client.get_paginator.return_value = paginator
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", return_value=client):
            result = fetch_bedrock_metrics()
        self.assertTrue(result["available"])
        self.assertEqual(result["by_model"], [])
        self.assertEqual(result["daily"], [])
        client.get_metric_data.assert_not_called()

    def test_client_error_access_denied_degrades_to_permission(self):
        client = _make_cloudwatch_client()
        client.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "no"}}, "ListMetrics"
        )
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", return_value=client):
            result = fetch_bedrock_metrics()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "permission")
        self.assertEqual(result["by_model"], [])
        self.assertEqual(result["today"], {"input_tokens": 0, "output_tokens": 0, "invocations": 0})

    def test_bedrock_error_degrades_to_unconfigured(self):
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", side_effect=BedrockError("no creds")):
            result = fetch_bedrock_metrics()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "unconfigured")

    def test_unexpected_error_degrades_to_error_reason(self):
        client = MagicMock()
        client.get_paginator.side_effect = RuntimeError("boom")
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", return_value=client):
            result = fetch_bedrock_metrics()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "error")

    def test_client_construction_db_error_degrades_to_error_reason(self):
        # A non-Bedrock failure while loading credentials (e.g. the credentials
        # table is unreachable) must degrade, not 500 the dashboard.
        with patch(f"{CLOUDWATCH_PATH}.get_cloudwatch_client", side_effect=RuntimeError("db down")):
            result = fetch_bedrock_metrics()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "error")

    def test_never_calls_cost_explorer(self):
        """boto3.client must never be invoked with "ce" anywhere in the flow."""
        real_client = _make_cloudwatch_client()

        def fake_boto3_client(service_name, **kwargs):
            self.assertNotEqual(service_name, "ce")
            return real_client

        with patch("boto3.client", side_effect=fake_boto3_client) as boto_client:
            # Drive the real client helper so boto3.client is actually exercised.
            from apps.core.models import AWSCredentialConfig

            AWSCredentialConfig.objects.create(
                name="AWS",
                is_active=True,
                access_key_id="key",
                secret_access_key="secret",
                default_region="us-west-2",
            )
            with patch(f"{CLOUDWATCH_PATH}.timezone.now", return_value=_ts(6)):
                fetch_bedrock_metrics()

        services_called = [call.args[0] for call in boto_client.call_args_list]
        self.assertIn("cloudwatch", services_called)
        self.assertNotIn("ce", services_called)
