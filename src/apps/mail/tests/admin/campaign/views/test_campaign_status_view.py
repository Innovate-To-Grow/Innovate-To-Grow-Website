from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.delivery.errors import UNEXPECTED_DELIVERY_ERROR
from apps.mail.tests.admin.campaign.views.test_campaign_views import _make_email_config


class CampaignStatusViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_status_view_renders_progress_page(self):
        campaign = EmailCampaign.objects.create(name="Status", subject="s", body="b", status="sending")

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status")
        self.assertContains(response, "data.status === 'queued' || data.status === 'sending'")
        self.assertContains(response, "Campaign Partially Sent")
        self.assertContains(response, "Campaign Failed")
        # Polling backs off on 429 (admin/js/poll-backoff.js) instead of reading the refusal as a status.
        self.assertContains(response, "admin/js/poll-backoff.js")

    def test_status_json_returns_progress_and_logs(self):
        campaign = EmailCampaign.objects.create(
            name="JSON",
            subject="s",
            body="b",
            status="sending",
            total_recipients=2,
            sent_count=1,
            failed_count=1,
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="sent@example.com",
            recipient_name="Sent",
            status="delivered",
            sent_at=timezone.now(),
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="failed@example.com",
            recipient_name="Failed",
            status="failed",
            error_message="bounced hard",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="pending@example.com",
            status="pending",
        )

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "sending")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["sent"], 1)
        self.assertEqual(payload["failed"], 1)
        self.assertIsNotNone(payload["started_at"])
        recent_emails = {row["email"] for row in payload["recent_logs"]}
        self.assertEqual(recent_emails, {"sent@example.com", "failed@example.com"})
        self.assertEqual(payload["failed_logs"][0]["error"], "bounced hard")

    def test_status_json_counts_queued_retrying_and_paused_recipients(self):
        campaign = EmailCampaign.objects.create(
            name="Counts", subject="s", body="b", status="sending", total_recipients=6
        )
        for index, status in enumerate(("pending", "processing", "retry", "paused", "paused", "sent")):
            RecipientLog.objects.create(campaign=campaign, email_address=f"r{index}@example.com", status=status)

        payload = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk])).json()

        self.assertEqual((payload["queued"], payload["retrying"], payload["paused"]), (3, 1, 2))

    def test_status_json_carries_the_email_channel_s_delivery_status(self):
        _make_email_config()
        campaign = EmailCampaign.objects.create(name="Limits", subject="s", body="b", status="sending")

        payload = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk])).json()

        delivery = payload["delivery"]
        self.assertFalse(delivery["held"])
        self.assertTrue(delivery["lines"][0].startswith("Now: "), delivery["lines"])
        self.assertTrue(delivery["lines"][1].startswith("Provider limit: "), delivery["lines"])

    def test_status_json_delivery_is_none_without_an_email_provider(self):
        EmailServiceConfig.objects.all().delete()
        campaign = EmailCampaign.objects.create(name="No mail", subject="s", body="b", status="sending")

        payload = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk])).json()

        self.assertIsNone(payload["delivery"])
        self.assertEqual((payload["queued"], payload["paused"]), (0, 0))

    def test_status_page_shows_the_paused_and_delivery_sections(self):
        campaign = EmailCampaign.objects.create(name="Status", subject="s", body="b", status="sending")

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status", args=[campaign.pk]))

        self.assertContains(response, 'id="count-paused"')
        self.assertContains(response, "Paused by limits")
        self.assertContains(response, 'id="delivery-section"')
        self.assertContains(response, "Resume paused recipients")
        self.assertContains(response, "paused by delivery limits")

    def test_status_json_keeps_curated_delivery_messages(self):
        campaign = EmailCampaign.objects.create(
            name="Needs review",
            subject="s",
            body="b",
            status="partial",
            error_message="Email delivery is not configured. Check Notification Delivery in admin.",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="uncertain@example.com",
            status="uncertain",
            error_message="Provider call outcome is uncertain; review before retrying.",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="crashed@example.com",
            status="failed",
            error_message=f"{UNEXPECTED_DELIVERY_ERROR} (RuntimeError)",
        )

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # Operator-authored text is the point of the live status page; only raw
        # exception text is kept out, and that happens where the row is written.
        self.assertEqual(payload["error_message"], campaign.error_message)
        errors = {row["email"]: row["error"] for row in payload["failed_logs"]}
        self.assertEqual(errors["uncertain@example.com"], "Provider call outcome is uncertain; review before retrying.")
        self.assertEqual(errors["crashed@example.com"], f"{UNEXPECTED_DELIVERY_ERROR} (RuntimeError)")

    def test_status_json_returns_cached_payload(self):
        campaign = EmailCampaign.objects.create(name="Cached", subject="s", body="b", status="sending")
        cache.set(f"mail:campaign_status:{campaign.pk}", {"status": "fromcache"}, 5)

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.json(), {"status": "fromcache"})


class CampaignStatusShortErrorTests(TestCase):
    def test_short_error_redacts_traceback(self):
        from apps.mail.admin.campaign.views.status import _short_error

        traceback_text = 'Traceback (most recent call last):\n  File "x.py", line 1'
        self.assertEqual(_short_error(traceback_text), "Send failed (see server logs for details).")

    def test_short_error_returns_empty_for_falsy(self):
        from apps.mail.admin.campaign.views.status import _short_error

        self.assertEqual(_short_error(""), "")

    def test_short_error_trims_first_line(self):
        from apps.mail.admin.campaign.views.status import _short_error

        self.assertEqual(_short_error("first line\nsecond line"), "first line")
