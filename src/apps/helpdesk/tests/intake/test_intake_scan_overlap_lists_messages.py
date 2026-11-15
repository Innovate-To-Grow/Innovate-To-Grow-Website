from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.core.models import EmailMonitorState, InboundMessage
from apps.core.services.email.bounces.scanning import state as bounce_state
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError
from apps.core.tests.services.email_monitoring.bounce_scan.test_bounce_scanner import FakeReader, listed
from apps.helpdesk.tests.intake.test_intake_scan import READER, IntakeTestCase, row

from ...models import HelpdeskSettings, IntakeState
from ...services.intake import scanner
from ...services.intake import state as intake_state
from ..corpus import SITE


class ScanTests(IntakeTestCase):
    def test_the_overlap_lists_messages_again_but_records_none_twice(self):
        self.scan()
        IntakeState.objects.filter(mailbox=SITE).update(checkpoint_at=self.ago(minutes=5))

        outcome = self.scan(bounce_scan_overlap_seconds=3600)

        self.assertEqual(outcome.stats, {"listed": 3, "recorded": 0})
        self.assertEqual(self.reader.since[-1], self.ago(minutes=65))
        self.assertEqual(InboundMessage.objects.count(), 3)

    def test_a_staff_lookback_sets_where_the_first_scan_starts(self):
        intake_state.set_lookback(SITE, 6)

        self.scan()

        self.assertEqual(self.reader.since, [self.ago(hours=6)])

    def test_a_rescan_reads_older_mail_and_records_only_what_is_new(self):
        older = listed("old-1", subject="Before the first scan", sender="lee@example.org", received=self.ago(days=5))
        reader = FakeReader([older, *self.messages], {})
        self.scan(reader, inbox_initial_lookback_hours=1)
        self.assertEqual(InboundMessage.objects.count(), 3)

        result = intake_state.rescan_since(SITE, self.ago(days=6), now=self.now)
        outcome = self.scan(reader)

        self.assertEqual(result.status, "moved")
        self.assertEqual(outcome.stats, {"listed": 4, "recorded": 1})
        self.assertTrue(InboundMessage.objects.filter(graph_id="old-1").exists())
        self.assertEqual(row().checkpoint_at, self.now)

    def test_a_scan_that_runs_out_of_pages_continues_from_what_it_recorded(self):
        outcome = self.scan(bounce_scan_page_size=2, bounce_scan_max_pages=1)

        self.assertEqual((outcome.status, outcome.stats), ("partial", {"listed": 2, "recorded": 2}))
        self.assertEqual(row().checkpoint_at, self.ago(minutes=40))

        follow_up = self.scan(bounce_scan_page_size=50, bounce_scan_overlap_seconds=0)

        self.assertEqual((follow_up.status, follow_up.stats["recorded"]), ("ok", 1))
        self.assertEqual(InboundMessage.objects.count(), 3)

    def test_a_page_of_messages_received_at_one_instant_cannot_hold_the_scan(self):
        same = self.ago(minutes=20)
        reader = FakeReader(
            [listed(f"m-{n}", subject="x", sender="a@example.org", received=same) for n in range(2)], {}
        )

        outcome = self.scan(reader, bounce_scan_page_size=2, bounce_scan_max_pages=3)

        # The second page starts at that instant and lists the same two again; the third starts a second later.
        self.assertEqual(reader.since[1:], [same, same + timedelta(seconds=1)])
        self.assertEqual((outcome.status, outcome.stats), ("ok", {"listed": 4, "recorded": 2}))

    def test_the_time_budget_ends_a_scan_with_its_progress_kept(self):
        with patch("apps.helpdesk.services.intake.scanner.time.monotonic", side_effect=[0.0, 1000.0]):
            outcome = self.scan(bounce_scan_max_seconds=5)

        self.assertEqual((outcome.status, outcome.stats["listed"]), ("partial", 0))
        self.assertIsNotNone(row().last_success_at)

    def test_a_message_without_a_received_time_is_left_alone(self):
        broken = {**listed("odd", subject="x", sender="a@example.org", received=self.ago(minutes=45))}
        broken["receivedDateTime"] = "not a time"
        reader = FakeReader([broken], {})

        def list_all(folder, since, limit):
            reader.since.append(since)
            return [broken]

        reader.list_received_since = list_all
        outcome = self.scan(reader)

        self.assertEqual(outcome.stats, {"listed": 1, "recorded": 0})
        self.assertFalse(InboundMessage.objects.exists())

    def test_microsofts_throttle_ends_the_scan_and_says_when_to_come_back(self):
        outcome = self.scan(FakeReader([], {}, list_error=GraphReadBusy(240)))

        state = row()
        self.assertEqual((outcome.status, outcome.retry_after), ("busy", 240))
        self.assertEqual((state.consecutive_failures, state.last_success_at, state.lease_token), (0, None, None))
        self.assertGreater(state.next_run_after, timezone.now() + timedelta(seconds=200))

    def test_a_failed_scan_is_recorded_for_the_card_with_a_scrubbed_error(self):
        outcome = self.scan(FakeReader([], {}, list_error=GraphReadError("Refused: Bearer abc.def")))

        state = row()
        self.assertEqual((outcome.status, state.consecutive_failures), ("failed", 1))
        self.assertEqual(state.last_error, "Refused: [redacted]")

        with (
            patch("apps.helpdesk.services.intake.scanner.inbound.record", side_effect=RuntimeError("db detail")),
            self.assertLogs("apps.helpdesk.services.intake.scanner", level="ERROR") as logs,
        ):
            unexpected = self.scan()

        self.assertEqual((unexpected.error, row().consecutive_failures), ("Unexpected RuntimeError", 2))
        self.assertNotIn("db detail", logs.records[0].getMessage())

    def test_nothing_is_read_while_switched_off_paused_or_already_scanning(self):
        HelpdeskSettings.objects.create(enabled=False)
        self.assertEqual(self.scan().status, "disabled")
        HelpdeskSettings.objects.update(enabled=True)

        intake_state.set_paused(SITE, True)
        self.assertEqual(self.scan().status, "paused")
        intake_state.set_paused(SITE, False)

        intake_state.acquire_lease(SITE, self.now)
        self.assertEqual(self.scan().status, "locked")

        self.assertEqual(self.reader.since, [])
        self.assertFalse(InboundMessage.objects.exists())

    def test_a_mailbox_the_site_may_not_read_is_shown_as_the_reason(self):
        with patch(READER, return_value=(None, SITE, "The scope does not grant read permission.")):
            outcome = scanner.scan_inbox()
        with patch(READER, return_value=(None, "", "Microsoft Graph is not configured.")):
            unconfigured = scanner.scan_inbox()

        self.assertEqual((outcome.status, row().last_error), ("inactive", "The scope does not grant read permission."))
        self.assertEqual((unconfigured.status, IntakeState.objects.count()), ("inactive", 1))

    def test_the_checkpoint_is_read_only_once_the_lease_is_held(self):
        """A rescan saved between looking at the row and taking the lease is still what the scan reads from."""
        IntakeState.objects.create(mailbox=SITE, checkpoint_at=self.ago(minutes=10))
        acquire = intake_state.acquire_lease

        def rescan_then_acquire(mailbox, now):
            IntakeState.objects.filter(mailbox=mailbox).update(checkpoint_at=self.ago(days=2))
            return acquire(mailbox, now)

        with patch("apps.helpdesk.services.intake.state.acquire_lease", side_effect=rescan_then_acquire):
            self.scan(bounce_scan_overlap_seconds=0)

        self.assertEqual(self.reader.since, [self.ago(days=2)])

    def test_the_intake_and_bounce_processing_never_move_each_other(self):
        bounce_state.state_for(SITE)
        EmailMonitorState.objects.filter(mailbox=SITE).update(checkpoint_at=self.ago(minutes=3), paused=True)

        self.scan()

        bounce = EmailMonitorState.objects.get(mailbox=SITE)
        self.assertEqual((bounce.checkpoint_at, bounce.paused, bounce.lease_token), (self.ago(minutes=3), True, None))
        self.assertEqual(InboundMessage.objects.count(), 3)  # bounce processing is paused, the intake is not
        bounce_state.rescan_since(SITE, self.ago(days=3), now=self.now)
        self.assertEqual(row().checkpoint_at, self.now)
