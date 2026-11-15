"""The SES delivery dashboard's AWS reads (CloudWatch metrics and the SES suppression list), shown on Email
Monitoring → Amazon SES. The tab itself is tested in ``apps.mail.tests.admin.email_monitoring.test_ses_admin``."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from apps.mail.services.campaign.dashboard import (
    PUBLIC_ERROR_MESSAGES,
    fetch_ses_cloudwatch_metrics,
    fetch_suppressed_destinations,
)


class MailDeliveryDashboardAwsServiceTest(TestCase):
    def test_fetch_ses_cloudwatch_metrics_uses_aws_metric_data(self):
        client = MagicMock()
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        client.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": "d0_attempts",
                    "Timestamps": [datetime(2026, 6, 7, 12, 0, tzinfo=UTC), now],
                    "Values": [20.0, 100.0],
                },
                {
                    "Id": "d0_success",
                    "Timestamps": [datetime(2026, 6, 7, 12, 0, tzinfo=UTC), now],
                    "Values": [19.0, 96.0],
                },
                {"Id": "d0_bounces", "Timestamps": [now], "Values": [3.0]},
                {"Id": "d0_complaints", "Timestamps": [now], "Values": [1.0]},
            ]
        }

        with patch("apps.mail.services.campaign.dashboard._cloudwatch_client", return_value=client):
            payload = fetch_ses_cloudwatch_metrics(days=183, now=now)

        self.assertTrue(payload["metrics"]["available"])
        self.assertEqual(payload["metrics"]["namespace"], "AWS/SES")
        self.assertEqual(payload["summary"]["attempts"], 120)
        self.assertEqual(payload["summary"]["success"], 115)
        self.assertEqual(payload["summary"]["problems"], 4)
        self.assertEqual(payload["summary"]["bounces"], 3)
        self.assertEqual(payload["summary"]["complaints"], 1)
        self.assertEqual(len(payload["daily"]), 183)
        today = payload["daily"][-1]
        self.assertEqual(today["date"], "2026-06-08")
        self.assertEqual(today["attempts"], 100)
        self.assertEqual(today["problems"], 4)
        sent_query = client.get_metric_data.call_args.kwargs["MetricDataQueries"][0]
        self.assertEqual(sent_query["MetricStat"]["Metric"]["Namespace"], "AWS/SES")
        self.assertEqual(sent_query["MetricStat"]["Metric"]["MetricName"], "Send")

    def test_fetch_suppressed_destinations_reads_aws_sesv2(self):
        client = MagicMock()
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        client.list_suppressed_destinations.side_effect = [
            {
                "SuppressedDestinationSummaries": [
                    {
                        "EmailAddress": "bounce@example.com",
                        "Reason": "BOUNCE",
                        "LastUpdateTime": datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
                    },
                    {
                        "EmailAddress": "complaint@example.com",
                        "Reason": "COMPLAINT",
                        "LastUpdateTime": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
                    },
                ],
                "NextToken": "page-2",
            },
            {
                "SuppressedDestinationSummaries": [
                    {
                        "EmailAddress": "older-bounce@example.com",
                        "Reason": "BOUNCE",
                        "LastUpdateTime": datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
                    }
                ],
            },
        ]

        with patch("apps.mail.services.campaign.dashboard._sesv2_client", return_value=client):
            rows, meta = fetch_suppressed_destinations(days=183, limit=50, now=now)

        self.assertTrue(meta["available"])
        self.assertEqual(meta["source"], "AWS SES account suppression list")
        self.assertEqual(meta["count"], 3)
        self.assertEqual(meta["returned_count"], 3)
        self.assertEqual(meta["total_count"], 3)
        self.assertFalse(meta["truncated"])
        self.assertEqual(meta["reason_counts"], {"BOUNCE": 2, "COMPLAINT": 1})
        self.assertEqual(
            [row["email"] for row in rows], ["bounce@example.com", "complaint@example.com", "older-bounce@example.com"]
        )
        self.assertEqual(rows[0]["source"], "AWS SES Suppression List")
        self.assertEqual(rows[0]["label"], "Bounced")
        self.assertEqual(rows[1]["label"], "Complained")
        first_call_kwargs = client.list_suppressed_destinations.call_args_list[0].kwargs
        second_call_kwargs = client.list_suppressed_destinations.call_args_list[1].kwargs
        self.assertEqual(first_call_kwargs["Reasons"], ["BOUNCE", "COMPLAINT"])
        self.assertEqual(first_call_kwargs["StartDate"], datetime(2025, 12, 7, 12, 0, tzinfo=UTC))
        self.assertEqual(first_call_kwargs["EndDate"], now)
        self.assertEqual(second_call_kwargs["NextToken"], "page-2")

    def test_fetch_suppressed_destinations_can_report_truncated_rows(self):
        client = MagicMock()
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        client.list_suppressed_destinations.return_value = {
            "SuppressedDestinationSummaries": [
                {
                    "EmailAddress": "bounce@example.com",
                    "Reason": "BOUNCE",
                    "LastUpdateTime": datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
                },
                {
                    "EmailAddress": "complaint@example.com",
                    "Reason": "COMPLAINT",
                    "LastUpdateTime": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
                },
            ]
        }

        with patch("apps.mail.services.campaign.dashboard._sesv2_client", return_value=client):
            rows, meta = fetch_suppressed_destinations(days=183, limit=1, now=now)

        self.assertEqual([row["email"] for row in rows], ["bounce@example.com"])
        self.assertEqual(meta["count"], 1)
        self.assertEqual(meta["returned_count"], 1)
        self.assertEqual(meta["total_count"], 2)
        self.assertTrue(meta["truncated"])
        self.assertEqual(meta["limit"], 1)

    def test_fetch_suppressed_destinations_returns_permission_diagnostics(self):
        client = MagicMock()
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        client.list_suppressed_destinations.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "User is not authorized to perform: ses:ListSuppressedDestinations",
                }
            },
            "ListSuppressedDestinations",
        )

        with patch("apps.mail.services.campaign.dashboard._sesv2_client", return_value=client):
            rows, meta = fetch_suppressed_destinations(days=183, limit=50, now=now)

        self.assertEqual(rows, [])
        self.assertFalse(meta["available"])
        self.assertEqual(meta["reason"], "permission")
        self.assertEqual(meta["error_code"], "AccessDeniedException")
        # The raw AWS exception text (ARNs, account ids, …) must never reach the
        # JSON payload — only the fixed public message does.
        self.assertNotIn("User is not authorized", meta["error_message"])
        self.assertEqual(meta["error_message"], PUBLIC_ERROR_MESSAGES["permission"])
        self.assertIn("ses:ListSuppressedDestinations", meta["required_actions"])
        self.assertIn("ses:GetSuppressedDestination", meta["required_actions"])

    def test_fetch_suppressed_destinations_hides_unexpected_exception_text(self):
        client = MagicMock()
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        client.list_suppressed_destinations.side_effect = RuntimeError("secret-internal-path /srv/app/creds")

        with patch("apps.mail.services.campaign.dashboard._sesv2_client", return_value=client):
            rows, meta = fetch_suppressed_destinations(days=183, limit=50, now=now)

        self.assertEqual(rows, [])
        self.assertFalse(meta["available"])
        self.assertEqual(meta["reason"], "error")
        self.assertEqual(meta["error_code"], "InternalError")
        self.assertNotIn("secret-internal-path", meta["error_message"])
        self.assertEqual(meta["error_message"], PUBLIC_ERROR_MESSAGES["error"])

    def test_fetch_suppressed_destinations_masks_unlisted_client_error_codes(self):
        client = MagicMock()
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        client.list_suppressed_destinations.side_effect = ClientError(
            {"Error": {"Code": "WeirdNewCode", "Message": "internal detail"}},
            "ListSuppressedDestinations",
        )

        with patch("apps.mail.services.campaign.dashboard._sesv2_client", return_value=client):
            rows, meta = fetch_suppressed_destinations(days=183, limit=50, now=now)

        self.assertEqual(rows, [])
        self.assertEqual(meta["reason"], "aws_error")
        # Codes outside the allowlist collapse to a generic identifier.
        self.assertEqual(meta["error_code"], "AwsError")
        self.assertEqual(meta["error_message"], PUBLIC_ERROR_MESSAGES["aws_error"])
