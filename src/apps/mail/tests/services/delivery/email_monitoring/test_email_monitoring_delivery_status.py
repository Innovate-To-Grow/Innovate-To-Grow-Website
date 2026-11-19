"""The dashboard's delivery evidence: a meaning for every delivery status, the delivered / no-bounce / quarantined or
spam counts, campaigns' failed recipients and comparison columns, and the no-bounce inference line of the card."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailMonitorState, EmailServiceConfig, OutboundEmail
from apps.core.tests.services.email_monitoring.helpers import (
    SENDER,
    GraphSendingMixin,
    make_email,
    monitoring_settings,
)
from apps.mail.models import EmailCampaign
from apps.mail.services.email_monitoring.dashboard import campaigns, detail, health, overview, scope, trace

DeliveryStatus = OutboundEmail.DeliveryStatus


class MeaningTests(TestCase):
    def test_every_delivery_status_has_a_meaning(self):
        self.assertEqual(set(detail.DELIVERY_MEANING), set(DeliveryStatus.values))

    def test_likely_and_trace_verdicts_say_what_they_do_not_prove(self):
        self.assertIn("not proof", detail.DELIVERY_MEANING[DeliveryStatus.NO_BOUNCE])
        self.assertIn("recipient's mail server", detail.DELIVERY_MEANING[DeliveryStatus.DELIVERED])
        self.assertIn("not proof it reached the inbox", detail.DELIVERY_MEANING[DeliveryStatus.DELIVERED])
        self.assertIn("message trace", detail.DELIVERY_MEANING[DeliveryStatus.FAILURE_CONFIRMED])

    def test_the_trace_facts_are_given_only_once_checked(self):
        checked = timezone.now()
        traced = make_email(
            delivery_status=DeliveryStatus.DELIVERED, trace_status="delivered", trace_checked_at=checked
        )

        self.assertEqual(detail.email_detail(traced)["trace"], {"status": "delivered", "checked_at": checked})
        self.assertIsNone(detail.email_detail(make_email())["trace"])


class CountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")
        for status in (
            DeliveryStatus.DELIVERED,
            DeliveryStatus.DELIVERED,
            DeliveryStatus.NO_BOUNCE,
            DeliveryStatus.QUARANTINED,
            DeliveryStatus.FILTERED_AS_SPAM,
            DeliveryStatus.FAILURE_CONFIRMED,
            DeliveryStatus.UNKNOWN,
        ):
            make_email(campaign_id=self.campaign.pk, delivery_status=status, recipient=f"{status}@example.com")

    def test_the_headline_figures_count_each_kind_of_evidence_apart(self):
        figures = overview.message_figures(OutboundEmail.objects.all())

        self.assertEqual(
            (figures["delivered"], figures["no_bounce"], figures["junk"], figures["bounced"]), (2, 1, 2, 1)
        )

    def test_the_campaign_comparison_has_delivered_and_junk_columns(self):
        [row] = campaigns.comparisons(scope.parse_scope({"range": "24h"}))

        self.assertEqual((row["delivered"], row["junk"], row["bounced"]), (2, 2, 1))

    def test_quarantined_and_spam_are_recipients_without_a_clean_result(self):
        failed, total = campaigns.failed_recipients(OutboundEmail.objects.all())

        self.assertEqual(total, 3)
        self.assertEqual(
            {email.delivery_status for email in failed},
            {DeliveryStatus.QUARANTINED, DeliveryStatus.FILTERED_AS_SPAM, DeliveryStatus.FAILURE_CONFIRMED},
        )


class InferenceLineTests(GraphSendingMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def line(self) -> dict:
        return health.monitoring_health()["trace"]["inference"]

    def test_it_waits_for_scan_coverage_until_the_scans_read_past_the_quiet_window(self):
        self.assertEqual(self.line()["status"], "waiting")
        now = timezone.now()
        EmailMonitorState.objects.create(mailbox=SENDER, scanned_since=now - timedelta(hours=1), checkpoint_at=now)
        self.assertEqual(self.line()["status"], "waiting")

    def test_it_is_active_once_the_scans_cover_a_full_window(self):
        now = timezone.now()
        state = EmailMonitorState.objects.create(
            mailbox=SENDER, scanned_since=now - timedelta(days=10), checkpoint_at=now
        )

        with monitoring_settings(no_bounce_after_hours=48):
            line = self.line()

        self.assertEqual((line["status"], line["since"], line["hours"]), ("active", state.scanned_since, 48))
        self.assertLess(line["until"], now - timedelta(hours=48))

    def test_paused_off_and_another_from_address_say_so(self):
        EmailMonitorState.objects.create(mailbox=SENDER, paused=True)
        self.assertEqual(self.line()["status"], "paused")
        with monitoring_settings(bounce_processing_enabled=False):
            self.assertEqual(self.line()["status"], "off")
        EmailServiceConfig.objects.update(from_email="someone-else@ucmerced.edu")
        self.assertIn(self.line()["status"], ("other_mailbox", "off"))

    def test_the_card_borrows_the_bounce_card_levels(self):
        self.assertEqual(set(trace.LEVELS.values()) - {"inactive", "waiting", "warning", "error", "ok"}, set())
        card = health.monitoring_health()["trace"]
        self.assertEqual((card["status"], card["level"], card["enabled"]), ("off", "inactive", False))
