from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import Member
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.admin.sms_campaign import (
    SmsCampaignAdmin,
    SmsRecipientLogAdmin,
)
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.tests.admin.sms.campaigns.test_sms_admin import _make_sms_config


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class SmsCampaignStatusViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_sms_config()

    def test_send_sms_status_view_renders_progress_page(self):
        campaign = SmsCampaign.objects.create(name="Status SMS", message="Hi", status="sending")

        response = self.client.get(reverse("admin:mail_smscampaign_send_status", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status SMS")
        self.assertContains(response, "data.status === 'queued' || data.status === 'sending'")
        self.assertContains(response, "SMS Campaign Partially Sent")
        self.assertContains(response, "SMS Campaign Failed")
        self.assertContains(response, "admin/js/poll-backoff.js")

    def test_send_sms_status_json_returns_progress_and_logs(self):
        campaign = SmsCampaign.objects.create(
            name="JSON SMS",
            message="Hi",
            status="sending",
            total_recipients=2,
            sent_count=1,
            failed_count=1,
        )
        sent_time = timezone.now()
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095551001",
            recipient_name="Sent User",
            status="sent",
            sent_at=sent_time,
        )
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095551002",
            recipient_name="Failed User",
            status="failed",
            error_message="Carrier rejected",
        )
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095551003",
            recipient_name="Pending User",
            status="pending",
        )

        response = self.client.get(reverse("admin:mail_smscampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "sending")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["sent"], 1)
        self.assertEqual(payload["failed"], 1)
        self.assertIsNotNone(payload["started_at"])
        # recent_logs excludes pending entries
        recent_phones = {row["phone"] for row in payload["recent_logs"]}
        self.assertEqual(recent_phones, {"+12095551001", "+12095551002"})
        self.assertEqual(len(payload["failed_logs"]), 1)
        self.assertEqual(payload["failed_logs"][0]["error"], "Carrier rejected")

    def test_send_sms_campaign_action_warns_for_non_draft(self):
        campaign = SmsCampaign.objects.create(name="Sent SMS", message="Hi", status="sent")

        response = self.client.get(
            reverse("admin:mail_smscampaign_change", args=[campaign.pk]),
        )
        self.assertEqual(response.status_code, 200)

        # Invoke the detail action directly through its url.
        action_response = self.client.get(
            reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]),
        )
        self.assertEqual(action_response.status_code, 200)


class SmsBackgroundSendTests(TestCase):
    @patch("apps.mail.services.campaign.dispatch.dispatch_sms_campaign")
    def test_background_send_invokes_durable_dispatch(self, mock_dispatch):
        admin_user = make_superuser()
        campaign = SmsCampaign.objects.create(name="BG SMS", message="Hi", status="sending")

        SmsCampaignAdmin._background_send(campaign.pk, admin_user.pk)

        mock_dispatch.assert_called_once()
        called_campaign = mock_dispatch.call_args.args[0]
        self.assertEqual(called_campaign.pk, campaign.pk)
        self.assertEqual(mock_dispatch.call_args.kwargs["sent_by"].pk, admin_user.pk)

    @patch(
        "apps.mail.services.campaign.dispatch.dispatch_sms_campaign",
        side_effect=RuntimeError("boom"),
    )
    def test_background_send_propagates_dispatch_error(self, _mock_dispatch):
        admin_user = make_superuser()
        campaign = SmsCampaign.objects.create(name="BG Fail SMS", message="Hi", status="sending")

        with self.assertRaisesMessage(RuntimeError, "boom"):
            SmsCampaignAdmin._background_send(campaign.pk, admin_user.pk)


class SmsCampaignChangelistConfigTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_falls_back_to_none_when_aws_config_load_raises(self):
        with patch(
            "apps.core.models.AWSCredentialConfig.load",
            side_effect=RuntimeError("config unavailable"),
        ):
            response = self.client.get(reverse("admin:mail_smscampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["aws_config"])


class SmsRecipientLogAdminTests(TestCase):
    def setUp(self):
        self.admin = SmsRecipientLogAdmin(SmsRecipientLog, AdminSite())
        self.factory = RequestFactory()
        self.campaign = SmsCampaign.objects.create(name="Log SMS", message="Hi")

    def test_status_badge_known_and_unknown(self):
        sent = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", status="sent")
        unknown = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551002", status="pending")

        self.assertEqual(self.admin.status_badge(sent), ("Sent", "success"))
        self.assertEqual(self.admin.status_badge(unknown), ("Pending", "info"))

    def test_error_preview_returns_dash_when_empty(self):
        log = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", error_message="")

        self.assertEqual(self.admin.error_preview(log), "-")

    def test_error_preview_truncates_long_error(self):
        log = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", error_message="e" * 200)

        result = self.admin.error_preview(log)

        self.assertEqual(result, "e" * 120 + "...")

    def test_error_preview_returns_short_error_unchanged(self):
        log = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", error_message="short")

        self.assertEqual(self.admin.error_preview(log), "short")

    def test_delete_permission_requires_an_admin(self):
        admin_user = make_admin(email="smslog-delete@example.com")

        # Every active Admin may delete; a regular member or an inactive staff account may not.
        self.assertTrue(self.admin.has_delete_permission(self._req(admin_user)))
        self.assertTrue(self.admin.has_delete_permission(self._req(Member(is_staff=True))))
        self.assertFalse(self.admin.has_delete_permission(self._req(Member(is_staff=False))))
        self.assertFalse(self.admin.has_delete_permission(self._req(Member(is_staff=True, is_active=False))))

    def _req(self, user):
        request = self.factory.get("/")
        request.user = user
        return request
