"""The SES delivery dashboard admin and its AWS reads."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.services.campaign.dashboard import (
    PUBLIC_ERROR_MESSAGES,
    fetch_ses_cloudwatch_metrics,
    fetch_suppressed_destinations,
)


class MailDeliveryDashboardAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.email_config = EmailServiceConfig.objects.create(
            name="Production Mail",
            is_active=True,
            from_email="admin@example.com",
            from_name="I2G Admin",
            max_send_rate=12,
        )
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="AKIATEST1234",
            secret_access_key="secret",
            default_region="us-west-2",
        )

    def _aws_dashboard_payload(self, *, window_days=183):
        return {
            "window_days": window_days,
            "generated_at": "2026-06-08T12:00:00+00:00",
            "summary": {
                "attempts": 120,
                "success": 116,
                "problems": 4,
                "failure_rate": 3.3,
                "campaign_attempts": 0,
                "campaign_errors": 0,
                "ticket_sent": 0,
                "ticket_errors": 0,
                "pending": 0,
                "bounces": 3,
                "complaints": 1,
                "rejected": 0,
                "failed": 0,
                "delayed": 0,
            },
            "aws": {
                "configured": True,
                "email_config": "Production Mail",
                "aws_config": "Primary AWS",
                "region": "us-west-2",
                "source_address": "I2G Admin <admin@example.com>",
                "send_rate": 12,
                "iam_key": "...1234",
                "metrics_available": True,
                "metrics_reason": "",
                "metrics_source": "CloudWatch account SES metrics",
                "recipient_details_available": True,
                "recipient_details_reason": "",
                "recipient_details_error_code": "",
                "recipient_details_error_message": "",
                "recipient_details_required_actions": [],
            },
            "metrics": {
                "available": True,
                "reason": "",
                "source": "CloudWatch account SES metrics",
                "namespace": "AWS/SES",
                "dimension_count": 1,
            },
            "recipient_details": {
                "available": True,
                "reason": "",
                "source": "AWS SES account suppression list",
                "count": 2,
                "error_code": "",
                "error_message": "",
                "required_actions": [],
                "returned_count": 2,
                "total_count": 2,
                "truncated": False,
                "limit": None,
                "reason_counts": {"BOUNCE": 1, "COMPLAINT": 1},
                "latest_seen": "Jun 08, 12:00",
                "window_days": window_days,
            },
            "daily": [{"date": "2026-06-08", "attempts": 120, "problems": 4}],
            "status_breakdown": [
                {"status": "bounced", "label": "Bounced", "count": 3},
                {"status": "complained", "label": "Complained", "count": 1},
                {"status": "delivered", "label": "Delivered", "count": 116},
            ],
            "problem_recipients": [
                {
                    "email": "bounce@example.com",
                    "name": "",
                    "source": "AWS SES Suppression List",
                    "context": "Account-level suppression",
                    "status": "bounced",
                    "label": "Bounced",
                    "reason": "BOUNCE",
                    "last_seen": "Jun 08, 12:00",
                    "count": 1,
                },
                {
                    "email": "complaint@example.com",
                    "name": "",
                    "source": "AWS SES Suppression List",
                    "context": "Account-level suppression",
                    "status": "complained",
                    "label": "Complained",
                    "reason": "COMPLAINT",
                    "last_seen": "Jun 07, 12:00",
                    "count": 1,
                },
            ],
        }

    @patch("apps.mail.admin.delivery_dashboard.admin.get_delivery_dashboard_data")
    def test_delivery_dashboard_renders_aws_metrics_and_problem_recipients(self, mock_dashboard_data):
        mock_dashboard_data.return_value = self._aws_dashboard_payload()

        response = self.client.get(reverse("admin:mail_delivery_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/mail/delivery_dashboard.html")
        self.assertContains(response, "AWS SES Delivery Dashboard")
        self.assertContains(response, "mail/css/delivery-dashboard.css?v=20260608-delivery-dashboard-deduped")
        self.assertContains(response, "mail-delivery-window-days")
        self.assertContains(response, "data-delivery-select-control")
        self.assertContains(response, "initializeDeliverySelects")
        self.assertContains(response, "mail-delivery-loading")
        self.assertContains(response, '<option value="7">Last 7 days</option>', html=True)
        self.assertContains(response, '<option value="90">Last 3 months</option>', html=True)
        self.assertContains(response, '<option value="183" selected>Last 6 months</option>', html=True)
        self.assertContains(response, '<option value="365">Last 12 months</option>', html=True)
        self.assertContains(response, "Problem Recipients")
        self.assertContains(response, "mail-delivery-recipient-search")
        self.assertContains(response, "mail-delivery-export-format")
        self.assertContains(response, "mail-delivery-export-recipients")
        self.assertContains(response, '<option value="csv">CSV</option>', html=True)
        self.assertContains(response, '<option value="tsv">TSV</option>', html=True)
        self.assertContains(response, '<option value="json">JSON</option>', html=True)
        self.assertContains(response, '<option value="xls">Excel</option>', html=True)
        self.assertContains(response, "Last 6 months AWS CloudWatch SES metrics")
        self.assertContains(response, "data-delivery-window-short")
        self.assertNotContains(response, "Problem Emails")
        self.assertNotContains(response, "i2g-delivery-group-table")
        self.assertContains(response, "AWS SES account suppression list")
        self.assertContains(response, "bounce@example.com")
        self.assertContains(response, "complaint@example.com")
        self.assertContains(response, "/admin/mail/delivery-dashboard/data/")
        mock_dashboard_data.assert_called_once_with(days=183)

    @patch("apps.mail.admin.delivery_dashboard.admin.get_delivery_dashboard_data")
    def test_delivery_dashboard_renders_selected_window(self, mock_dashboard_data):
        mock_dashboard_data.return_value = self._aws_dashboard_payload(window_days=365)

        response = self.client.get(reverse("admin:mail_delivery_dashboard"), {"days": "365"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="365" selected>Last 12 months</option>', html=True)
        mock_dashboard_data.assert_called_once_with(days=365)

    @patch("apps.mail.admin.delivery_dashboard.admin.get_delivery_dashboard_data")
    def test_delivery_dashboard_data_returns_aws_payload(self, mock_dashboard_data):
        mock_dashboard_data.return_value = self._aws_dashboard_payload()

        response = self.client.get(reverse("admin:mail_delivery_dashboard_data"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["window_days"], 183)
        self.assertEqual(payload["summary"]["attempts"], 120)
        self.assertEqual(payload["summary"]["success"], 116)
        self.assertEqual(payload["summary"]["problems"], 4)
        self.assertEqual(payload["summary"]["bounces"], 3)
        self.assertEqual(payload["summary"]["complaints"], 1)
        self.assertTrue(payload["metrics"]["available"])
        self.assertEqual(payload["metrics"]["namespace"], "AWS/SES")
        self.assertTrue(payload["recipient_details"]["available"])
        self.assertFalse(payload["recipient_details"]["truncated"])
        self.assertEqual(payload["recipient_details"]["total_count"], 2)
        self.assertTrue(payload["aws"]["configured"])
        self.assertEqual(payload["aws"]["region"], "us-west-2")
        problem_emails = {row["email"] for row in payload["problem_recipients"]}
        self.assertIn("bounce@example.com", problem_emails)
        self.assertIn("complaint@example.com", problem_emails)
        self.assertNotIn("problem_groups", payload)
        self.assertNotIn("campaign_errors", payload)
        status_labels = {row["label"] for row in payload["status_breakdown"]}
        self.assertIn("Bounced", status_labels)
        self.assertIn("Complained", status_labels)
        mock_dashboard_data.assert_called_once_with(days=183)

    @patch("apps.mail.admin.delivery_dashboard.admin.get_delivery_dashboard_data")
    def test_delivery_dashboard_data_accepts_allowed_window(self, mock_dashboard_data):
        mock_dashboard_data.side_effect = lambda *, days=183: self._aws_dashboard_payload(window_days=days)

        response = self.client.get(reverse("admin:mail_delivery_dashboard_data"), {"days": "90"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["window_days"], 90)
        mock_dashboard_data.assert_called_once_with(days=90)

    @patch("apps.mail.admin.delivery_dashboard.admin.get_delivery_dashboard_data")
    def test_delivery_dashboard_data_rejects_unlisted_window(self, mock_dashboard_data):
        mock_dashboard_data.side_effect = lambda *, days=183: self._aws_dashboard_payload(window_days=days)

        response = self.client.get(reverse("admin:mail_delivery_dashboard_data"), {"days": "999"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["window_days"], 183)
        mock_dashboard_data.assert_called_once_with(days=183)

    def test_delivery_dashboard_requires_mail_admin_access(self):
        other_admin = make_admin(apps=["cms"], email="cmsadmin@example.com")
        self.client.force_login(other_admin)

        response = self.client.get(reverse("admin:mail_delivery_dashboard"))

        self.assertEqual(response.status_code, 403)


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
