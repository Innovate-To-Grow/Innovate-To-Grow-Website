from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.core.models import EmailBounce, EmailMonitorState
from apps.core.services.email.bounces.scanning import state
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError
from apps.core.tests.services.email_monitoring.bounce_scan.test_bounce_scanner import FakeReader, _ScannerCase

from ..helpers import SENDER


class ScannerTests(_ScannerCase):
    def test_a_second_scan_never_opens_or_records_a_report_again(self):
        reader = FakeReader(self.messages, self.bodies)
        self.scan(reader)
        EmailMonitorState.objects.update(checkpoint_at=None)

        outcome = self.scan(reader)

        self.assertEqual(outcome.stats["already_processed"], 1)
        self.assertEqual(reader.opened.count("ndr-1"), 1)
        self.assertEqual(EmailBounce.objects.count(), 1)

    def test_a_busy_read_keeps_the_progress_and_waits_as_microsoft_asked(self):
        reader = FakeReader(self.messages, self.bodies, fetch_error=GraphReadBusy(90))

        outcome = self.scan(reader)

        self.assertEqual((outcome.status, outcome.retry_after), ("busy", 90))
        monitor = EmailMonitorState.objects.get(mailbox=SENDER)
        self.assertEqual(monitor.consecutive_failures, 0)
        self.assertIsNone(monitor.last_success_at)
        self.assertGreater(monitor.next_run_after, timezone.now())

    def test_a_refused_read_is_a_failed_scan_shown_on_the_state(self):
        reader = FakeReader([], {}, list_error=GraphReadError("Microsoft Graph denied access to i2g@ucmerced.edu."))

        outcome = self.scan(reader)
        self.scan(reader)

        self.assertEqual(outcome.status, "failed")
        monitor = EmailMonitorState.objects.get(mailbox=SENDER)
        self.assertEqual(monitor.consecutive_failures, 2)
        self.assertEqual(monitor.last_error, "Microsoft Graph denied access to i2g@ucmerced.edu.")
        self.assertIsNone(monitor.lease_token)

    def test_an_unexpected_error_is_recorded_by_type_only(self):
        reader = FakeReader([], {}, list_error=RuntimeError("detail that may echo request values"))

        outcome = self.scan(reader)

        self.assertEqual(outcome.error, "Unexpected RuntimeError")
        self.assertEqual(EmailMonitorState.objects.get().last_error, "Unexpected RuntimeError")

    def test_a_report_that_cannot_be_parsed_is_kept_as_unknown(self):
        reader = FakeReader(self.messages[:1], self.bodies)

        with patch("apps.core.services.email.bounces.scanning.scanner.parse_report", side_effect=ValueError("broken")):
            outcome = self.scan(reader)

        bounce = EmailBounce.objects.get()
        self.assertEqual((outcome.status, bounce.classification, bounce.recipient), ("ok", "unknown", ""))

    def test_the_message_budget_ends_a_scan_early_with_the_checkpoint_at_what_was_done(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader, bounce_scan_max_messages=1)

        self.assertEqual((outcome.status, reader.opened), ("partial", ["ndr-1"]))
        checkpoint = EmailMonitorState.objects.get().checkpoint_at
        self.assertEqual(checkpoint, self.now - timedelta(minutes=20))

    def test_the_time_budget_ends_a_scan_before_it_opens_more_reports(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader, bounce_scan_max_seconds=0)

        self.assertEqual((outcome.status, reader.opened), ("partial", []))

    def test_a_report_the_database_refuses_is_skipped_and_counted(self):
        from django.db import DataError

        reader = FakeReader(self.messages, self.bodies)

        with patch("apps.core.services.email.bounces.scanning.scanner.save_report", side_effect=DataError("bad data")):
            outcome = self.scan(reader)

        self.assertEqual((outcome.status, outcome.stats["unstorable"]), ("ok", 1))
        self.assertEqual(EmailMonitorState.objects.get().checkpoint_at, self.now)

    def test_a_paused_mailbox_is_skipped(self):
        state.set_paused(SENDER, True)
        reader = FakeReader(self.messages, self.bodies)

        self.assertEqual(self.scan(reader).status, "paused")
        self.assertEqual(reader.opened, [])

    def test_is_paused_says_whether_the_dashboard_paused_the_mailbox(self):
        self.assertFalse(state.is_paused(SENDER))  # no state row yet
        state.set_paused(SENDER, True)
        self.assertTrue(state.is_paused(SENDER))
        self.assertFalse(state.is_paused("other@ucmerced.edu"))
        state.set_paused(SENDER, False)
        self.assertFalse(state.is_paused(SENDER))

    def test_a_running_scan_holds_the_mailbox(self):
        state.state_for(SENDER)
        self.assertIsNotNone(state.acquire_lease(SENDER, self.now))

        self.assertEqual(self.scan(FakeReader(self.messages, self.bodies)).status, "locked")

    def test_an_expired_lease_is_taken_over(self):
        state.state_for(SENDER)
        state.acquire_lease(SENDER, self.now - timedelta(hours=2))

        self.assertEqual(self.scan(FakeReader(self.messages, self.bodies)).status, "ok")

    def test_switched_off_it_does_nothing(self):
        reader = FakeReader(self.messages, self.bodies)

        self.assertEqual(self.scan(reader, bounce_processing_enabled=False).status, "disabled")
        self.assertEqual(reader.opened, [])
