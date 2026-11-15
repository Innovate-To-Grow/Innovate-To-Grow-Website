from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.core.services.background_jobs.metrics import publish_worker_metrics
from apps.core.tests.services.platform.jobs.test_background_jobs import (
    METRICS,
    METRICS_CLIENT,
    METRICS_REGION,
    stubbed_cloudwatch,
)


@override_settings(BACKGROUND_JOB_METRICS_NAMESPACE="I2G/Workers", AWS_S3_REGION_NAME=METRICS_REGION)
class PublishWorkerMetricsTests(SimpleTestCase):
    def test_puts_every_metric_with_its_unit_in_the_namespace(self):
        client, stubber = stubbed_cloudwatch()
        stubber.add_response(
            "put_metric_data",
            {},
            {
                "Namespace": "I2G/Workers",
                "MetricData": [
                    {"MetricName": "WorkerHeartbeat", "Value": 1.0, "Unit": "Count"},
                    {"MetricName": "QueueDepth", "Value": 3.0, "Unit": "Count"},
                    {"MetricName": "OldestJobAge", "Value": 12.5, "Unit": "Seconds"},
                    {"MetricName": "FailedJobs", "Value": 0.0, "Unit": "Count"},
                    {"MetricName": "UncertainJobs", "Value": 2.0, "Unit": "Count"},
                ],
            },
        )

        with stubber, patch(METRICS_CLIENT, return_value=client) as factory:
            publish_worker_metrics(METRICS)

        stubber.assert_no_pending_responses()
        factory.assert_called_once_with("cloudwatch", region_name=METRICS_REGION)

    def test_provider_error_is_logged_not_raised(self):
        client, stubber = stubbed_cloudwatch()
        stubber.add_client_error("put_metric_data", service_error_code="Throttling", http_status_code=400)

        with (
            stubber,
            patch(METRICS_CLIENT, return_value=client),
            self.assertLogs("apps.core.services.background_jobs.metrics", level="ERROR") as logs,
        ):
            publish_worker_metrics(METRICS)

        self.assertIn("Could not publish background worker metrics", logs.output[0])

    @override_settings(BACKGROUND_JOB_METRICS_NAMESPACE="")
    def test_no_namespace_means_no_client(self):
        with patch(METRICS_CLIENT) as factory:
            publish_worker_metrics(METRICS)

        factory.assert_not_called()
