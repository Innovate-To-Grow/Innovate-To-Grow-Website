"""The delivery dashboard's own CloudWatch and SESv2 clients, built for real and answered by botocore's Stubber.

The admin tests replace ``_cloudwatch_client`` / ``_sesv2_client`` with mocks; here the factories run, so the client
options and each request are validated against the service models botocore ships.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import boto3
from botocore.stub import ANY, Stubber
from django.test import SimpleTestCase, override_settings

from apps.core.services.aws.credentials import AwsCredentials
from apps.mail.services.campaign.dashboard import fetch_ses_cloudwatch_metrics, fetch_suppressed_destinations

DASHBOARD = "apps.mail.services.campaign.dashboard"
REGION = "us-west-2"
CREDS = AwsCredentials(access_key_id="test-access-key", secret_access_key="test-secret-key", region=REGION)
NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


class DashboardAwsClientTests(SimpleTestCase):
    def stub_client(self, service, operation, response, expected_params):
        """Patch the dashboard's boto3.client so it builds a real client whose ``operation`` is stubbed."""
        real_client = boto3.client
        built = {}

        def build(service_name, **kwargs):
            client = real_client(service_name, **kwargs)
            stubber = Stubber(client)
            stubber.add_response(operation, response, expected_params)
            stubber.activate()
            self.addCleanup(stubber.deactivate)
            built.update(service=service_name, kwargs=kwargs, stubber=stubber)
            return client

        for patcher in (
            patch(f"{DASHBOARD}.resolve_aws_credentials", return_value=CREDS),
            patch(f"{DASHBOARD}.boto3.client", side_effect=build),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        return built

    def assert_built_with_shared_credentials(self, built, service):
        self.assertEqual(built["service"], service)
        self.assertEqual(
            built["kwargs"],
            {"region_name": REGION, "aws_access_key_id": "test-access-key", "aws_secret_access_key": "test-secret-key"},
        )
        built["stubber"].assert_no_pending_responses()

    def test_suppressed_destinations_come_from_a_real_sesv2_client(self):
        built = self.stub_client(
            "sesv2",
            "list_suppressed_destinations",
            {
                "SuppressedDestinationSummaries": [
                    {"EmailAddress": "bounce@example.com", "Reason": "BOUNCE", "LastUpdateTime": NOW},
                ]
            },
            {"Reasons": ["BOUNCE", "COMPLAINT"], "StartDate": NOW - timedelta(days=7), "EndDate": NOW, "PageSize": 100},
        )

        rows, meta = fetch_suppressed_destinations(days=7, now=NOW)

        self.assert_built_with_shared_credentials(built, "sesv2")
        self.assertTrue(meta["available"])
        self.assertEqual(meta["reason_counts"], {"BOUNCE": 1, "COMPLAINT": 0})
        self.assertEqual([(row["email"], row["status"]) for row in rows], [("bounce@example.com", "bounced")])

    @override_settings(SES_CONFIGURATION_SET_NAME="")
    def test_ses_metrics_come_from_a_real_cloudwatch_client(self):
        built = self.stub_client(
            "cloudwatch",
            "get_metric_data",
            {"MetricDataResults": [{"Id": "d0_attempts", "Timestamps": [NOW], "Values": [5.0]}]},
            {
                "MetricDataQueries": ANY,  # still validated against the model, just not compared
                "StartTime": NOW - timedelta(days=7),
                "EndTime": NOW,
                "ScanBy": "TimestampAscending",
            },
        )

        payload = fetch_ses_cloudwatch_metrics(days=7, now=NOW)

        self.assert_built_with_shared_credentials(built, "cloudwatch")
        self.assertTrue(payload["metrics"]["available"])
        self.assertEqual(payload["metrics"]["source"], "CloudWatch account SES metrics")
        self.assertEqual(payload["summary"]["attempts"], 5)
