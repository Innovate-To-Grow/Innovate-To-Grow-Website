"""No-bounce inference (``bounces.recording.quiet``): an accepted Graph email becomes "No bounce received" only once
the bounce scan has provably read its sending mailbox well past the send, and never when a report may be about it."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailCategory, EmailMonitorState, EmailServiceConfig, OutboundEmail
from apps.core.services.email.bounces.recording.quiet import mark_quiet_emails, no_bounce_after_hours, quiet_until

from ..helpers import SENDER, GraphSendingMixin, make_bounce, make_email, monitoring_settings

DeliveryStatus = OutboundEmail.DeliveryStatus


class QuietCase(GraphSendingMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.now = timezone.now()
        self.state = EmailMonitorState.objects.create(
            mailbox=SENDER, scanned_since=self.now - timedelta(days=10), checkpoint_at=self.now
        )

    def email(self, *, hours_ago: float, **values) -> OutboundEmail:
        accepted = self.now - timedelta(hours=hours_ago)
        values.setdefault("mailbox", SENDER)
        return make_email(accepted_at=accepted, last_attempt_at=accepted, **values)

    def mark(self, **settings_changes) -> int:
        self.state.refresh_from_db()
        with monitoring_settings(**settings_changes):
            return mark_quiet_emails(self.state)

    def status(self, email) -> str:
        email.refresh_from_db()
        return email.delivery_status


class CoverageTests(QuietCase):
    def test_only_emails_inside_what_the_scan_read_are_marked(self):
        covered = self.email(hours_ago=72)
        too_recent = self.email(hours_ago=47)
        before_coverage = self.email(hours_ago=24 * 11)

        self.assertEqual(self.mark(no_bounce_after_hours=48), 1)

        self.assertEqual(self.status(covered), DeliveryStatus.NO_BOUNCE)
        self.assertEqual(self.status(too_recent), DeliveryStatus.UNKNOWN)
        self.assertEqual(self.status(before_coverage), DeliveryStatus.UNKNOWN)

    def test_the_margin_is_the_quiet_window_the_overlap_and_the_clock_skew(self):
        with monitoring_settings(no_bounce_after_hours=48, bounce_scan_overlap_seconds=900):
            until = quiet_until(self.state)

        self.assertEqual(self.now - until, timedelta(hours=48, minutes=25))
        just_inside = self.email(hours_ago=48 + 26 / 60)
        just_outside = self.email(hours_ago=48 + 24 / 60)

        self.mark(no_bounce_after_hours=48, bounce_scan_overlap_seconds=900)

        self.assertEqual(self.status(just_inside), DeliveryStatus.NO_BOUNCE)
        self.assertEqual(self.status(just_outside), DeliveryStatus.UNKNOWN)

    def test_nothing_is_marked_before_the_scan_coverage_is_known(self):
        email = self.email(hours_ago=72)
        EmailMonitorState.objects.filter(pk=self.state.pk).update(scanned_since=None)

        self.assertEqual(self.mark(), 0)
        EmailMonitorState.objects.filter(pk=self.state.pk).update(scanned_since=self.now, checkpoint_at=None)
        self.assertEqual(self.mark(), 0)
        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_nothing_is_marked_while_paused_or_switched_off(self):
        email = self.email(hours_ago=72)

        EmailMonitorState.objects.filter(pk=self.state.pk).update(paused=True)
        self.assertEqual(self.mark(), 0)
        EmailMonitorState.objects.filter(pk=self.state.pk).update(paused=False)
        self.assertEqual(self.mark(bounce_processing_enabled=False), 0)

        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_the_quiet_window_never_exceeds_the_match_window(self):
        with monitoring_settings(no_bounce_after_hours=500, bounce_match_window_hours=120):
            self.assertEqual(no_bounce_after_hours(), 120)
        with monitoring_settings(no_bounce_after_hours=0):
            self.assertEqual(no_bounce_after_hours(), 1)


class ScopeTests(QuietCase):
    def test_probes_other_mailboxes_providers_and_unaccepted_emails_are_left_alone(self):
        left = [
            self.email(hours_ago=72, category=EmailCategory.ACCESS_CHECK),
            self.email(hours_ago=72, mailbox="other@ucmerced.edu"),
            self.email(hours_ago=72, provider="ses"),
            self.email(hours_ago=72, status=OutboundEmail.Status.UNCERTAIN),
        ]

        self.assertEqual(self.mark(), 0)

        for email in left:
            with self.subTest(email=email.pk):
                email.refresh_from_db()
                self.assertNotEqual(email.delivery_status, DeliveryStatus.NO_BOUNCE)

    def test_nothing_is_marked_when_the_from_address_is_another_mailbox(self):
        email = self.email(hours_ago=72)
        EmailServiceConfig.objects.filter(pk=self.service_config.pk).update(from_email="noreply@ucmerced.edu")

        self.assertEqual(self.mark(), 0)
        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_only_unknown_statuses_move(self):
        delayed = self.email(hours_ago=72, delivery_status=DeliveryStatus.DELAYED)
        failed = self.email(hours_ago=72, delivery_status=DeliveryStatus.FAILURE_CONFIRMED)

        self.assertEqual(self.mark(), 0)

        self.assertEqual(self.status(delayed), DeliveryStatus.DELAYED)
        self.assertEqual(self.status(failed), DeliveryStatus.FAILURE_CONFIRMED)


class UnmatchedReportTests(QuietCase):
    def test_an_unmatched_report_for_the_recipient_after_the_send_keeps_it_unknown(self):
        email = self.email(hours_ago=72, recipient="maybe@example.com")
        make_bounce(recipient="maybe@example.com", received_at=self.now - timedelta(hours=70))

        self.assertEqual(self.mark(), 0)
        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_a_report_stamped_slightly_before_the_send_on_exchanges_clock_keeps_it_unknown(self):
        email = self.email(hours_ago=72, recipient="fast@example.com")
        make_bounce(recipient="fast@example.com", received_at=email.accepted_at - timedelta(seconds=5))

        self.assertEqual(self.mark(), 0)
        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_an_unmatched_report_naming_no_recipient_keeps_it_unknown(self):
        email = self.email(hours_ago=72)
        make_bounce(recipient="", received_at=self.now - timedelta(hours=70))

        self.assertEqual(self.mark(), 0)
        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_an_earlier_report_or_one_for_another_recipient_does_not_block(self):
        email = self.email(hours_ago=72, recipient="fine@example.com")
        make_bounce(recipient="fine@example.com", received_at=self.now - timedelta(hours=80))
        make_bounce(recipient="someone-else@example.com", received_at=self.now - timedelta(hours=70))

        self.assertEqual(self.mark(), 1)
        self.assertEqual(self.status(email), DeliveryStatus.NO_BOUNCE)

    def test_a_report_matched_to_another_email_does_not_block(self):
        email = self.email(hours_ago=72, recipient="fine@example.com")
        other = self.email(hours_ago=73, recipient="fine@example.com", delivery_status=DeliveryStatus.FAILURE_CONFIRMED)
        make_bounce(recipient="fine@example.com", received_at=self.now - timedelta(hours=70), email=other)

        self.assertEqual(self.mark(), 1)
        self.assertEqual(self.status(email), DeliveryStatus.NO_BOUNCE)

    def test_a_multi_recipient_email_waits_for_any_unmatched_report_in_the_mailbox(self):
        recipients = ["a@example.com", "b@example.com"]
        email = self.email(hours_ago=72, recipient="a@example.com", recipients=recipients, recipient_count=2)
        make_bounce(recipient="b@example.com", received_at=self.now - timedelta(hours=70))

        self.assertEqual(self.mark(), 0)
        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)
