"""The pacing notice on the campaign confirmation page."""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.models import BackgroundJob, EmailServiceConfig
from apps.core.services.background_jobs import claim_jobs, enqueue_job
from apps.core.tests.graph_helpers import create_graph_config
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign import pacing
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.campaign.pacing import campaign_job_spacing, delivery_pacing_notice, format_duration

# Graph senders used in this module; the mailbox scope rules have their own tests.
GRAPH_TEST_SCOPE = ("sender@example.com", "admin@example.com")

TENANT_ID = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class FormatDurationTests(SimpleTestCase):
    def test_durations_are_rounded_to_whole_minutes_with_a_minimum_of_one(self):
        cases = {
            1: "1 minute",
            30: "1 minute",
            60: "1 minute",
            2500: "42 minutes",
            3600: "1 hour",
            3900: "1 hour 5 minutes",
            7500: "2 hours 5 minutes",
            7200: "2 hours",
        }
        for seconds, expected in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(format_duration(seconds), expected)


class DeliveryPacingNoticeTests(TestCase):
    def email(self, provider="graph", **overrides):
        values = {"name": "Mail", "is_active": True, "provider": provider, "from_email": "sender@example.com"}
        return EmailServiceConfig.objects.create(**values | overrides)

    def make_graph(self, **overrides):
        values = {
            "name": "Graph",
            "is_active": True,
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
        }
        return create_graph_config(scope=GRAPH_TEST_SCOPE, **values | overrides)

    def test_providers_without_extra_limits_get_no_notice(self):
        for provider in ("ses", "smtp"):
            with self.subTest(provider):
                EmailServiceConfig.objects.all().delete()
                self.assertIsNone(delivery_pacing_notice(self.email(provider), 5000))

    def test_an_empty_campaign_gets_no_notice(self):
        self.assertIsNone(delivery_pacing_notice(self.email(), 0))

    def test_graph_shows_the_rate_the_duration_and_the_daily_cap(self):
        self.make_graph(messages_per_minute=24)

        notice = delivery_pacing_notice(self.email(), 1000)

        self.assertEqual(notice["provider"], "Microsoft Graph")
        self.assertEqual(notice["rate"], "24 emails/min")
        self.assertEqual(notice["duration"], "42 minutes")
        self.assertEqual(notice["daily_limit"], 10_000)
        self.assertFalse(notice["over_daily_limit"])

    def test_more_recipients_than_the_daily_cap_is_flagged(self):
        self.assertTrue(delivery_pacing_notice(self.email(), 10_001)["over_daily_limit"])
        self.assertFalse(delivery_pacing_notice(self.email(), 10_000)["over_daily_limit"])

    def test_the_notice_says_whether_failed_recipients_are_retried(self):
        config = self.email()
        for enabled in (True, False):
            with self.subTest(enabled=enabled), override_settings(BACKGROUND_JOBS_ENABLED=enabled):
                self.assertIs(delivery_pacing_notice(config, 10)["retries_enabled"], enabled)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ConfirmPageNoticeTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        make_member(email="alice@example.com")
        self.campaign = EmailCampaign.objects.create(
            name="Spring Update", subject="Hi", body="Body", audience_type="all_members", status="draft"
        )
        self.url = reverse("admin:mail_emailcampaign_send_confirm", args=[self.campaign.pk])

    def use_graph(self):
        create_graph_config(
            scope=GRAPH_TEST_SCOPE,
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
        )
        EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="graph", from_email="sender@example.com"
        )

    def test_a_graph_campaign_shows_the_pacing_notice(self):
        self.use_graph()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Microsoft Graph limits how fast this mailbox can send.")
        self.assertContains(response, "24 emails/min")
        self.assertContains(response, "10000 recipients per day")
        self.assertNotContains(response, "more recipients than that daily limit")

    def test_the_notice_warns_when_the_campaign_exceeds_the_daily_cap(self):
        self.use_graph()

        with patch.object(pacing, "GRAPH_DAILY_RECIPIENT_LIMIT", 1):
            response = self.client.get(self.url)

        self.assertContains(response, "more recipients than that daily limit")
        self.assertContains(response, "confirm-send-btn")

    def test_the_notice_mentions_disabled_background_jobs(self):
        self.use_graph()
        with override_settings(BACKGROUND_JOBS_ENABLED=False):
            response = self.client.get(self.url)
            self.assertContains(response, "Background jobs are disabled")
            self.assertContains(response, "A deploy or restart in that time stops it")
        with override_settings(BACKGROUND_JOBS_ENABLED=True):
            self.assertNotContains(self.client.get(self.url), "Background jobs are disabled")

    def test_ses_campaigns_have_no_notice(self):
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="a@example.com")

        response = self.client.get(self.url)

        self.assertNotContains(response, "limits how fast this mailbox can send")


def make_graph_sender(messages_per_minute=24):
    create_graph_config(
        scope=GRAPH_TEST_SCOPE,
        name="Graph",
        is_active=True,
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        messages_per_minute=messages_per_minute,
    )
    return EmailServiceConfig.objects.create(
        name="Mail", is_active=True, provider="graph", from_email="sender@example.com"
    )


class CampaignJobSpacingTests(TestCase):
    def test_graph_spaces_recipient_jobs_at_its_pace(self):
        self.assertAlmostEqual(campaign_job_spacing(make_graph_sender(messages_per_minute=24)), 2.5)

    def test_ses_and_smtp_queue_every_recipient_at_once(self):
        for provider in ("ses", "smtp"):
            with self.subTest(provider):
                self.assertEqual(campaign_job_spacing(EmailServiceConfig(provider=provider, max_send_rate=1)), 0.0)

    def test_the_active_config_is_used_by_default(self):
        make_graph_sender(messages_per_minute=30)

        self.assertAlmostEqual(campaign_job_spacing(), 2.0)


class QueuedCampaignSpacingTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()
        self.campaign = EmailCampaign.objects.create(
            name="Spaced",
            subject="Hi",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="a@example.com\nb@example.com\nc@example.com",
        )

    def campaign_jobs(self):
        return list(BackgroundJob.objects.filter(kind="mail.email_recipient").order_by("available_at", "created_at"))

    def test_graph_recipient_jobs_become_due_one_pace_apart_and_logs_mirror_them(self):
        make_graph_sender(messages_per_minute=24)

        queue_email_campaign(self.campaign, sent_by=self.sender)

        jobs = self.campaign_jobs()
        offsets = [(job.available_at - jobs[0].available_at).total_seconds() for job in jobs]
        self.assertEqual(offsets, [0.0, 2.5, 5.0])
        for job in jobs:
            log = RecipientLog.objects.get(pk=job.payload["recipient_log_id"])
            self.assertEqual(log.available_at, job.available_at)

    def test_work_queued_during_a_graph_campaign_runs_before_its_later_recipients(self):
        make_graph_sender(messages_per_minute=24)
        queue_email_campaign(self.campaign, sent_by=self.sender)
        enqueue_job(kind="event.ticket_email", dedupe_key="later", payload={})

        claimed = claim_jobs(batch_size=10)

        # A ticket (transactional, priority 10) is claimed even before the campaign recipient already due.
        self.assertEqual([job.kind for job in claimed], ["event.ticket_email", "mail.email_recipient"])

    def test_ses_campaign_jobs_are_all_due_at_once(self):
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="a@example.com")

        queue_email_campaign(self.campaign, sent_by=self.sender)

        self.assertEqual(len({job.available_at for job in self.campaign_jobs()}), 1)
        self.assertEqual(len(claim_jobs(batch_size=10)), 3)
