from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.cms.models import CMSPage
from apps.core.models import AWSCredentialConfig, EmailServiceConfig, GmailAccessAccount
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign
from apps.mail.services import GMAIL_FOLDER_DISPLAY
from apps.mail.services.delivery_dashboard import (
    fetch_ses_cloudwatch_metrics,
    fetch_suppressed_destinations,
    get_delivery_dashboard_data,
)
from apps.mail.services.preview import HTML_MARKER


class MailSettingsAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = EmailServiceConfig.objects.create(
            name="Production Mail",
            is_active=True,
            ses_from_email="admin@example.com",
            ses_from_name="I2G Admin",
            ses_max_send_rate=12,
        )
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
            sms_message_template="Your I2G code is {code}.",
        )

    def test_settings_page_shows_notification_delivery_config(self):
        response = self.client.get(reverse("admin:mail_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Delivery")
        self.assertContains(response, "AWS Identity and Access Management (IAM)")
        self.assertContains(response, "Primary AWS")
        self.assertContains(response, "Production Mail")
        self.assertContains(response, "Amazon Simple Email Service (us-west-2)")
        self.assertContains(response, "Amazon Simple Notification Service (us-west-2)")
        self.assertContains(response, "I2G Admin")
        self.assertContains(response, "admin@example.com")
        self.assertContains(response, "...-key")
        self.assertContains(response, "Configured")
        self.assertContains(response, "Your I2G code is {code}.")
        self.assertContains(response, 'href="/admin/mail/settings/edit/"')
        self.assertContains(response, 'href="/admin/mail/settings/test-email/"')
        self.assertContains(response, 'href="/admin/mail/settings/test-sms/"')
        self.assertNotContains(response, 'name="email-name"')
        self.assertNotContains(response, "Save Notification Delivery")
        self.assertNotContains(response, "Gmail Fallback")
        self.assertNotContains(response, "smtp.gmail.com")

    def test_settings_page_shows_not_configured_when_aws_is_missing(self):
        AWSCredentialConfig.objects.all().delete()

        response = self.client.get(reverse("admin:mail_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amazon Simple Email Service not configured")
        self.assertContains(response, "Amazon Simple Notification Service not configured")

    def test_settings_edit_view_renders_notification_delivery_form(self):
        response = self.client.get(reverse("admin:mail_settings_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email-name"')
        self.assertContains(response, 'name="aws-access_key_id"')
        self.assertContains(response, "Save Notification Delivery")
        self.assertContains(response, 'href="/admin/mail/settings/"')

    def test_settings_edit_post_updates_notification_delivery_config(self):
        response = self.client.post(
            reverse("admin:mail_settings_edit"),
            {
                "email-name": "Updated Mail",
                "email-is_active": "on",
                "email-ses_from_name": "Updated Sender",
                "email-ses_from_email": "updated@example.com",
                "email-ses_max_send_rate": "8",
                "aws-name": "Updated AWS",
                "aws-is_active": "on",
                "aws-access_key_id": "updated-key",
                "aws-secret_access_key": "updated-secret",
                "aws-default_region": "us-east-1",
                "aws-sms_from_number": "+12065550123",
                "aws-sms_message_template": "Code: {code}",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        self.config.refresh_from_db()
        self.aws_config.refresh_from_db()
        self.assertEqual(self.config.name, "Updated Mail")
        self.assertEqual(self.config.ses_from_email, "updated@example.com")
        self.assertEqual(self.config.ses_max_send_rate, 8)
        self.assertEqual(self.aws_config.name, "Updated AWS")
        self.assertEqual(self.aws_config.default_region, "us-east-1")
        self.assertEqual(self.aws_config.sms_from_number, "+12065550123")

    def test_test_email_view_renders_form(self):
        response = self.client.get(reverse("admin:mail_settings_test_email"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test Email")
        self.assertContains(response, "admin@example.com")

    def test_test_sms_view_renders_form(self):
        response = self.client.get(reverse("admin:mail_settings_test_sms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test SMS")
        self.assertContains(response, "AWS SNS")

    @patch("apps.mail.admin.settings._send_test_email")
    def test_test_email_post_uses_active_mail_config(self, mock_send_test_email):
        mock_send_test_email.return_value = "AWS SES"

        response = self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        mock_send_test_email.assert_called_once()
        self.assertEqual(mock_send_test_email.call_args.kwargs["config"].pk, self.config.pk)
        self.assertEqual(mock_send_test_email.call_args.kwargs["recipient"], "ops@example.com")

    @patch("apps.mail.admin.settings._send_test_sms")
    def test_test_sms_post_uses_notification_delivery_config(self, mock_send_test_sms):
        mock_send_test_sms.return_value = "message (ID: sns-1)"

        response = self.client.post(
            reverse("admin:mail_settings_test_sms"),
            {"country_code": "+1", "recipient": "2065550123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        mock_send_test_sms.assert_called_once_with(phone_number="+12065550123")

    def test_test_email_post_without_recipient_shows_error(self):
        response = self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "  "}, follow=True)

        self.assertContains(response, "Please provide a recipient email address")

    @patch("apps.mail.admin.settings._send_test_email", side_effect=RuntimeError("SES boom"))
    def test_test_email_post_reports_send_failure(self, mock_send):
        response = self.client.post(
            reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"}, follow=True
        )

        self.assertContains(response, "Failed to send test email: SES boom")

    def test_test_sms_post_without_recipient_shows_error(self):
        response = self.client.post(
            reverse("admin:mail_settings_test_sms"), {"country_code": "+1", "recipient": ""}, follow=True
        )

        self.assertContains(response, "Please provide a phone number")

    @patch("apps.mail.admin.settings._send_test_sms", side_effect=RuntimeError("SNS boom"))
    def test_test_sms_post_reports_send_failure(self, mock_send):
        response = self.client.post(
            reverse("admin:mail_settings_test_sms"),
            {"country_code": "+1", "recipient": "2065550123"},
            follow=True,
        )

        self.assertContains(response, "Failed to send test SMS: SNS boom")


class MailDeliveryDashboardAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.email_config = EmailServiceConfig.objects.create(
            name="Production Mail",
            is_active=True,
            ses_from_email="admin@example.com",
            ses_from_name="I2G Admin",
            ses_max_send_rate=12,
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
            "problem_groups": [
                {
                    "name": "example.com",
                    "type": "Recipient domain",
                    "source": "AWS SES Suppression List",
                    "problems": 2,
                    "bounces": 1,
                    "complaints": 1,
                    "rejected": 0,
                    "failed": 0,
                    "latest_seen": "Jun 08, 12:00",
                    "sample_email": "bounce@example.com",
                }
            ],
            "campaign_errors": [
                {
                    "name": "example.com",
                    "type": "Recipient domain",
                    "source": "AWS SES Suppression List",
                    "problems": 2,
                    "bounces": 1,
                    "complaints": 1,
                    "rejected": 0,
                    "failed": 0,
                    "latest_seen": "Jun 08, 12:00",
                    "sample_email": "bounce@example.com",
                }
            ],
        }

    @patch("apps.mail.admin.delivery_dashboard.get_delivery_dashboard_data")
    def test_delivery_dashboard_renders_aws_metrics_and_problem_recipients(self, mock_dashboard_data):
        mock_dashboard_data.return_value = self._aws_dashboard_payload()

        response = self.client.get(reverse("admin:mail_delivery_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/mail/delivery_dashboard.html")
        self.assertContains(response, "AWS SES Delivery Dashboard")
        self.assertContains(response, "mail/css/delivery-dashboard.css?v=20260608-delivery-dashboard-email-ranking")
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
        self.assertContains(response, "Problem Emails")
        self.assertContains(response, "i2g-delivery-group-table")
        self.assertContains(response, "Failures")
        self.assertContains(response, "AWS SES account suppression list")
        self.assertContains(response, "bounce@example.com")
        self.assertContains(response, "complaint@example.com")
        self.assertContains(response, "/admin/mail/delivery-dashboard/data/")
        mock_dashboard_data.assert_called_once_with(days=183)

    @patch("apps.mail.admin.delivery_dashboard.get_delivery_dashboard_data")
    def test_delivery_dashboard_renders_selected_window(self, mock_dashboard_data):
        mock_dashboard_data.return_value = self._aws_dashboard_payload(window_days=365)

        response = self.client.get(reverse("admin:mail_delivery_dashboard"), {"days": "365"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="365" selected>Last 12 months</option>', html=True)
        mock_dashboard_data.assert_called_once_with(days=365)

    @patch("apps.mail.admin.delivery_dashboard.get_delivery_dashboard_data")
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
        self.assertEqual(payload["problem_groups"][0]["name"], "example.com")
        self.assertEqual(payload["problem_groups"][0]["problems"], 2)
        status_labels = {row["label"] for row in payload["status_breakdown"]}
        self.assertIn("Bounced", status_labels)
        self.assertIn("Complained", status_labels)
        mock_dashboard_data.assert_called_once_with(days=183)

    @patch("apps.mail.admin.delivery_dashboard.get_delivery_dashboard_data")
    def test_delivery_dashboard_data_accepts_allowed_window(self, mock_dashboard_data):
        mock_dashboard_data.side_effect = lambda *, days=183: self._aws_dashboard_payload(window_days=days)

        response = self.client.get(reverse("admin:mail_delivery_dashboard_data"), {"days": "90"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["window_days"], 90)
        mock_dashboard_data.assert_called_once_with(days=90)

    @patch("apps.mail.admin.delivery_dashboard.get_delivery_dashboard_data")
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
    @patch("apps.mail.services.delivery_dashboard.fetch_suppressed_destinations")
    @patch("apps.mail.services.delivery_dashboard.fetch_ses_cloudwatch_metrics")
    def test_delivery_dashboard_builds_aws_problem_groups(self, mock_metrics, mock_recipients):
        mock_metrics.return_value = {
            "summary": {
                "attempts": 10,
                "success": 8,
                "problems": 2,
                "failure_rate": 20,
                "bounces": 1,
                "complaints": 1,
            },
            "daily": [],
            "status_breakdown": [],
            "metrics": {
                "available": True,
                "reason": "",
                "source": "CloudWatch account SES metrics",
                "namespace": "AWS/SES",
                "dimension_count": 1,
            },
        }
        mock_recipients.return_value = (
            [
                {
                    "email": "one@example.com",
                    "source": "AWS SES Suppression List",
                    "context": "Account-level suppression",
                    "status": "bounced",
                    "label": "Bounced",
                    "reason": "BOUNCE",
                    "last_seen": "Jun 08, 12:00",
                    "count": 1,
                },
                {
                    "email": "one@example.com",
                    "source": "AWS SES Suppression List",
                    "context": "Account-level suppression",
                    "status": "complained",
                    "label": "Complained",
                    "reason": "COMPLAINT",
                    "last_seen": "Jun 07, 12:00",
                    "count": 1,
                },
                {
                    "email": "two@example.com",
                    "source": "AWS SES Suppression List",
                    "context": "Account-level suppression",
                    "status": "bounced",
                    "label": "Bounced",
                    "reason": "BOUNCE",
                    "last_seen": "Jun 06, 12:00",
                    "count": 1,
                },
            ],
            {
                "available": True,
                "reason": "",
                "source": "AWS SES account suppression list",
                "count": 3,
                "error_code": "",
                "error_message": "",
                "required_actions": [],
            },
        )

        payload = get_delivery_dashboard_data(days=183)

        self.assertEqual(payload["problem_groups"][0]["name"], "one@example.com")
        self.assertEqual(payload["problem_groups"][0]["domain"], "example.com")
        self.assertEqual(payload["problem_groups"][0]["problems"], 2)
        self.assertEqual(payload["problem_groups"][0]["bounces"], 1)
        self.assertEqual(payload["problem_groups"][0]["complaints"], 1)
        self.assertEqual(payload["problem_groups"][1]["name"], "two@example.com")
        self.assertEqual(payload["campaign_errors"], payload["problem_groups"])

    @patch("apps.mail.services.delivery_dashboard.fetch_suppressed_destinations")
    @patch("apps.mail.services.delivery_dashboard.fetch_ses_cloudwatch_metrics")
    def test_delivery_dashboard_returns_all_aws_problem_groups(self, mock_metrics, mock_recipients):
        mock_metrics.return_value = {
            "summary": {
                "attempts": 20,
                "success": 5,
                "problems": 15,
                "failure_rate": 75,
                "bounces": 15,
                "complaints": 0,
            },
            "daily": [],
            "status_breakdown": [],
            "metrics": {
                "available": True,
                "reason": "",
                "source": "CloudWatch account SES metrics",
                "namespace": "AWS/SES",
                "dimension_count": 1,
            },
        }
        rows = [
            {
                "email": f"user{i}@domain{i}.example",
                "source": "AWS SES Suppression List",
                "context": "Account-level suppression",
                "status": "bounced",
                "label": "Bounced",
                "reason": "BOUNCE",
                "last_seen": "Jun 08, 12:00",
                "count": 1,
            }
            for i in range(15)
        ]
        mock_recipients.return_value = (
            rows,
            {
                "available": True,
                "reason": "",
                "source": "AWS SES account suppression list",
                "count": 15,
                "total_count": 15,
                "error_code": "",
                "error_message": "",
                "required_actions": [],
            },
        )

        payload = get_delivery_dashboard_data(days=183)

        group_names = {group["name"] for group in payload["problem_groups"]}
        self.assertEqual(len(payload["problem_groups"]), 15)
        self.assertIn("user14@domain14.example", group_names)
        self.assertEqual(payload["campaign_errors"], payload["problem_groups"])

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

        with patch("apps.mail.services.delivery_dashboard._cloudwatch_client", return_value=client):
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

        with patch("apps.mail.services.delivery_dashboard._sesv2_client", return_value=client):
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

        with patch("apps.mail.services.delivery_dashboard._sesv2_client", return_value=client):
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

        with patch("apps.mail.services.delivery_dashboard._sesv2_client", return_value=client):
            rows, meta = fetch_suppressed_destinations(days=183, limit=50, now=now)

        self.assertEqual(rows, [])
        self.assertFalse(meta["available"])
        self.assertEqual(meta["reason"], "permission")
        self.assertEqual(meta["error_code"], "AccessDeniedException")
        self.assertIn("ses:ListSuppressedDestinations", meta["error_message"])
        self.assertIn("ses:ListSuppressedDestinations", meta["required_actions"])
        self.assertIn("ses:GetSuppressedDestination", meta["required_actions"])


class EmailCampaignAdminImportTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = EmailCampaign.objects.create(
            subject="Spring Update",
            body="Draft body",
            login_redirect_path="/account",
        )
        self.gmail_import_config = GmailAccessAccount.objects.create(
            name="Primary Gmail Access Account",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )
        from apps.core.models import AWSCredentialConfig

        AWSCredentialConfig.objects.all().delete()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="AKIAXXXXXXXX",
            secret_access_key="secret",
            default_region="us-west-2",
        )
        self.email_config = EmailServiceConfig.objects.create(
            name="Primary SES",
            is_active=True,
            ses_from_email="campaigns@ucmerced.edu",
            ses_from_name="Innovate to Grow",
        )

    def test_changelist_shows_loaded_gmail_import_account_and_mailboxes(self):
        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gmail Access Account")
        self.assertContains(response, "imap.gmail.com")
        self.assertContains(response, "campaigns@ucmerced.edu")
        self.assertContains(response, GMAIL_FOLDER_DISPLAY)
        self.assertContains(response, "Innovate to Grow &lt;campaigns@ucmerced.edu&gt;")
        self.assertContains(response, 'href="/admin/mail/settings/"')
        self.assertContains(response, "Edit Notification Delivery")

    def test_import_gmail_html_view_renders_recent_messages(self):
        with patch("apps.mail.admin.campaign.list_recent_sent_messages") as mock_list:
            mock_list.return_value = [
                {
                    "message_id": "msg-1",
                    "subject": "Sent Newsletter",
                    "sent_at": "2026-04-06 09:00 AM PDT",
                    "snippet": "Recent Gmail snippet",
                    "has_html": True,
                }
            ]

            response = self.client.get(reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=5, mailbox="campaigns@ucmerced.edu", force_refresh=False)
        self.assertContains(response, "Sent Newsletter")
        self.assertContains(response, "Import will replace the current campaign body")
        self.assertContains(response, "imap.gmail.com")
        self.assertContains(response, "campaigns@ucmerced.edu")
        self.assertContains(response, GMAIL_FOLDER_DISPLAY)

    def test_import_gmail_html_view_redirects_for_non_draft_campaign(self):
        self.campaign.status = "sent"
        self.campaign.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]),
        )

    def test_import_gmail_html_confirm_overwrites_body(self):
        def _fake_import(campaign, message_id, mailbox):
            campaign.body = HTML_MARKER + "<p>Imported from Gmail</p>"
            campaign.save(update_fields=["body", "updated_at"])
            return campaign.body

        with patch("apps.mail.admin.campaign.import_message_into_campaign", side_effect=_fake_import) as mock_import:
            response = self.client.post(
                reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
                {"message_id": "msg-1"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]),
        )
        mock_import.assert_called_once_with(self.campaign, "msg-1", mailbox="campaigns@ucmerced.edu")
        self.campaign.refresh_from_db()
        self.assertTrue(self.campaign.body.startswith(HTML_MARKER))
        self.assertIn("Imported from Gmail", self.campaign.body)

    def test_send_preview_remains_available_for_imported_html(self):
        self.campaign.body = HTML_MARKER + "<p><strong>Imported</strong> HTML</p>"
        self.campaign.save(update_fields=["body", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_send_preview", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview Email")

    def test_change_view_renders_for_sent_campaign(self):
        self.campaign.status = "sent"
        self.campaign.login_redirect_path = "/event-registration"
        self.campaign.save(update_fields=["status", "login_redirect_path", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.campaign.subject)


class MailAdminPerAppAccessTest(TestCase):
    """End-to-end per-app gate via the Django admin test client.

    A staff member with ``mail`` in ``admin_apps`` may reach mail changelists but
    is denied changelists in apps they were not granted; superusers reach both.
    """

    def test_mail_staff_can_view_mail_changelist(self):
        make_admin(apps=["mail"], email="mail-only@example.com")
        self.client.login(username="mail-only@example.com", password="testpass123")

        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_mail_staff_denied_non_mail_changelist(self):
        make_admin(apps=["mail"], email="mail-only2@example.com")
        self.client.login(username="mail-only2@example.com", password="testpass123")

        response = self.client.get(reverse("admin:event_event_changelist"))

        self.assertEqual(response.status_code, 403)

    def test_other_app_staff_denied_mail_changelist(self):
        make_admin(apps=["cms"], email="cms-only@example.com")
        self.client.login(username="cms-only@example.com", password="testpass123")

        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view_both_changelists(self):
        make_superuser(email="su-peraccess@example.com")
        self.client.login(username="su-peraccess@example.com", password="testpass123")

        mail_response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))
        event_response = self.client.get(reverse("admin:event_event_changelist"))

        self.assertEqual(mail_response.status_code, 200)
        self.assertEqual(event_response.status_code, 200)


class EmailCampaignAdminRedirectTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.request_factory = RequestFactory()
        self.model_admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.published_page = CMSPage.objects.create(
            slug="campaign-destination",
            route="/campaign-destination",
            title="Campaign Destination",
            status="published",
        )
        self.archived_page = CMSPage.objects.create(
            slug="old-campaign-destination",
            route="/old-campaign-destination",
            title="Old Campaign Destination",
            status="archived",
        )

    def test_new_campaign_form_requires_redirect_destination(self):
        form = self._get_form(
            data={
                "audience_type": "subscribers",
                "member_email_scope": "primary",
                "subject": "Spring Update",
                "body_format": "plain",
                "body": "Draft body",
                "login_redirect_path": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("login_redirect_path", form.errors)

    def test_redirect_choices_include_account_app_routes_and_published_cms_pages(self):
        form = self._get_form()
        choices = dict(form.fields["login_redirect_path"].choices)

        self.assertIn("/account", choices)
        self.assertIn("/schedule", choices)
        self.assertIn("/campaign-destination", choices)
        self.assertNotIn("/old-campaign-destination", choices)

    def test_sent_campaign_marks_redirect_destination_read_only(self):
        campaign = EmailCampaign.objects.create(
            subject="Sent Update",
            body="Sent body",
            login_redirect_path="/campaign-destination",
            status="sent",
        )

        readonly_fields = self.model_admin.get_readonly_fields(self._build_request(), obj=campaign)

        self.assertIn("login_redirect_path", readonly_fields)

    def _get_form(self, *, data=None, instance=None):
        form_class = self.model_admin.get_form(self._build_request(), obj=instance)
        return form_class(data=data, instance=instance)

    def _build_request(self):
        request = self.request_factory.get("/admin/mail/emailcampaign/")
        request.user = self.admin_user
        return request
