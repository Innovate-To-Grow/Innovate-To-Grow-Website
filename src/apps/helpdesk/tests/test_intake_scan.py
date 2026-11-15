"""The helpdesk's intake: its own scan of the Inbox (separate from bounce processing), its state (lease, checkpoint,
pause, "Rescan since", first-scan lookback), its background jobs and what the cards show of it. Microsoft Graph is
never contacted: the reader is a fake listing a fixed Inbox."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob, EmailMonitorState, InboundMessage
from apps.core.services.background_jobs import claim_jobs, registered_job_kinds, run_claimed_job
from apps.core.services.email.bounces import state as bounce_state
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError
from apps.core.services.email.inbound import InboxReader, registered_inbox_readers
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.core.tests.services.email_monitoring.test_bounce_scanner import FakeReader, listed

from ..models import HelpdeskSettings, IntakeState, Ticket
from ..services.ingest import jobs as ingest_jobs
from ..services.intake import jobs, scanner, status
from ..services.intake import state as intake_state
from . import corpus
from .corpus import SITE
from .helpers import make_admin

READER = "apps.helpdesk.services.intake.scanner.active_reader"
STATUS_READER = "apps.helpdesk.services.intake.status.active_reader"
INGEST_READER = "apps.helpdesk.services.ingest.runner.active_reader"
Status = InboundMessage.Status


def intake_jobs():
    return BackgroundJob.objects.filter(kind=jobs.INTAKE_JOB_KIND)


def ingest_runs():
    return BackgroundJob.objects.filter(kind=ingest_jobs.INGEST_JOB_KIND)


def row() -> IntakeState:
    return IntakeState.objects.get(mailbox=SITE)


class IntakeTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now().replace(microsecond=0)
        self.messages = [
            listed(
                "ndr-1", subject="Undeliverable: Hello", sender="postmaster@x.example", received=self.ago(minutes=50)
            ),
            listed("human-1", subject="Question", sender="pat@example.org", received=self.ago(minutes=40)),
            listed("human-2", subject="Thanks", sender="sam@example.org", received=self.ago(minutes=30)),
        ]
        self.messages[1]["conversationId"] = "AAQkConversation1"
        self.reader = FakeReader(self.messages, {})

    def ago(self, **delta):
        return self.now - timedelta(**delta)

    def scan(self, reader=None, **settings_changes):
        reader = reader or self.reader
        with patch(READER, return_value=(reader, SITE, "")), monitoring_settings(**settings_changes):
            return scanner.scan_inbox(now=self.now)


class ScanTests(IntakeTestCase):
    def test_the_first_scan_records_every_listed_message_once_and_moves_the_checkpoint(self):
        outcome = self.scan(inbox_initial_lookback_hours=24)

        self.assertEqual((outcome.status, outcome.mailbox), ("ok", SITE))
        self.assertEqual(outcome.stats, {"listed": 3, "recorded": 3})
        self.assertEqual(self.reader.since, [self.ago(hours=24)])
        rows = {item.graph_id: item for item in InboundMessage.objects.all()}
        self.assertEqual(set(rows), {"ndr-1", "human-1", "human-2"})
        self.assertEqual(rows["ndr-1"].kind, InboundMessage.Kind.BOUNCE_CANDIDATE)
        self.assertEqual((rows["human-1"].kind, rows["human-1"].conversation_id), ("message", "AAQkConversation1"))
        self.assertEqual({item.status for item in rows.values()}, {Status.PENDING})
        state = row()
        self.assertEqual((state.checkpoint_at, state.consecutive_failures, state.lease_token), (self.now, 0, None))
        self.assertIsNotNone(state.last_success_at)
        self.assertEqual(state.last_run_stats, {"listed": 3, "recorded": 3})
        self.assertEqual(self.reader.opened, [])  # it opens nothing: the ingest reads each message later

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


class StateTests(IntakeTestCase):
    def test_the_lease_lets_one_scan_run_and_an_expired_one_is_taken_over(self):
        intake_state.state_for(SITE)

        self.assertIsNotNone(intake_state.acquire_lease(SITE, self.now))
        self.assertIsNone(intake_state.acquire_lease(SITE, self.now + timedelta(minutes=1)))
        later = self.now + timedelta(seconds=901)
        self.assertIsNotNone(intake_state.acquire_lease(SITE, later))

    def test_a_row_another_process_created_meanwhile_is_used(self):
        created = IntakeState.objects.create(mailbox=SITE)

        with patch.object(IntakeState.objects, "get_or_create", side_effect=IntegrityError("duplicate key")):
            self.assertEqual(intake_state.state_for(SITE).pk, created.pk)

    def test_a_scan_whose_lease_was_released_saves_nothing(self):
        intake_state.state_for(SITE)
        token = intake_state.acquire_lease(SITE, self.ago(hours=1))
        intake_state.rescan_since(SITE, self.ago(days=1), now=self.now)  # the lease expired: released

        intake_state.finish(SITE, token, checkpoint=self.now, stats={"listed": 1})

        self.assertEqual((row().checkpoint_at, row().last_run_stats), (self.ago(days=1), {}))

    def test_pause_and_resume_are_recorded_once_each(self):
        staff = make_admin(apps=["helpdesk"], email="agent@example.com")

        self.assertTrue(intake_state.set_paused(SITE, True, actor=staff))
        self.assertFalse(intake_state.set_paused(SITE, True, actor=staff))
        with self.assertLogs("apps.helpdesk.services.intake.state", level="INFO") as logs:
            self.assertTrue(intake_state.set_paused(SITE, False))

        self.assertEqual(list(LogEntry.objects.values_list("change_message", flat=True)), ["Intake paused."])
        self.assertIn("action=resume mailbox=i2g@ucmerced.edu actor=-", logs.records[0].getMessage())
        self.assertFalse(intake_state.is_paused(SITE))

    def test_the_lookback_is_bounded_audited_and_clamped_whatever_the_row_holds(self):
        staff = make_admin(apps=["helpdesk"], email="agent@example.com")
        with monitoring_settings(inbox_max_lookback_days=10, inbox_initial_lookback_hours=72):
            self.assertEqual(intake_state.lookback_bounds(), (1, 240))
            with self.assertRaises(ValueError):
                intake_state.set_lookback(SITE, 241)
            self.assertIsNone(intake_state.set_lookback(SITE, 200, actor=staff))
            self.assertEqual(intake_state.set_lookback(SITE, 200, actor=staff), 200)
            IntakeState.objects.filter(mailbox=SITE).update(initial_lookback_hours=5000)
            self.assertEqual(intake_state.lookback_hours(row()), 240)
            self.assertEqual(intake_state.lookback_hours(None), 72)
        with monitoring_settings(inbox_initial_lookback_hours=0):
            self.assertEqual(intake_state.default_lookback_hours(), 1)

        self.assertEqual(LogEntry.objects.get().change_message, "First-scan lookback: default (72 h) → 200 h.")

    def test_a_rescan_moves_the_checkpoint_back_only_when_that_is_safe(self):
        staff = make_admin(apps=["helpdesk"], email="agent@example.com")
        IntakeState.objects.create(mailbox=SITE, checkpoint_at=self.ago(minutes=10))
        with monitoring_settings(inbox_max_lookback_days=30):
            self.assertEqual(
                intake_state.rescan_since(SITE, self.now + timedelta(hours=1), now=self.now).status, "future"
            )
            self.assertEqual(intake_state.rescan_since(SITE, self.ago(days=31), now=self.now).status, "too_early")
            self.assertEqual(intake_state.rescan_since(SITE, self.ago(minutes=5), now=self.now).status, "not_earlier")
            intake_state.acquire_lease(SITE, self.now)
            running = intake_state.rescan_since(SITE, self.ago(days=1), now=self.now)
            IntakeState.objects.filter(mailbox=SITE).update(lease_until=None, lease_token=None, paused=True)
            moved = intake_state.rescan_since(SITE, self.ago(days=1), actor=staff, now=self.now)

        self.assertEqual((running.status, running.previous), ("running", self.ago(minutes=10)))
        self.assertEqual((moved.status, moved.previous, moved.paused), ("moved", self.ago(minutes=10), True))
        self.assertEqual((row().checkpoint_at, row().paused), (self.ago(days=1), True))
        self.assertIn("Rescan since", LogEntry.objects.get().change_message)
        self.assertFalse(EmailMonitorState.objects.exists())
        self.assertEqual(str(row()), f"Helpdesk intake for {SITE}")


class JobTests(IntakeTestCase):
    def run_job(self, reader=None):
        with patch(READER, return_value=(reader or self.reader, SITE, "")):
            jobs.run_intake_job(job=None)

    def test_the_job_kind_and_the_card_description_are_registered(self):
        kind = registered_job_kinds()[jobs.INTAKE_JOB_KIND]

        self.assertEqual((kind.family, kind.lane), (None, None))
        self.assertEqual(registered_inbox_readers()["helpdesk"], "apps.helpdesk.services.intake.status.describe")

    def test_the_cadence_is_the_inbox_interval_with_a_quicker_catch_up(self):
        self.assertEqual((jobs.interval_seconds(), jobs.catch_up_seconds()), (120, 30))
        with monitoring_settings(inbox_scan_interval_seconds=10):
            self.assertEqual((jobs.interval_seconds(), jobs.catch_up_seconds()), (60, 30))
        self.assertEqual(jobs.next_delay(None), 120)
        self.assertEqual(jobs.next_delay(scanner.IntakeOutcome("ok")), 120)
        self.assertEqual(jobs.next_delay(scanner.IntakeOutcome("partial")), 30)
        self.assertEqual(jobs.next_delay(scanner.IntakeOutcome("busy", retry_after=900)), 900)
        self.assertEqual(jobs.next_delay(scanner.IntakeOutcome("busy", retry_after=10)), 120)

    def test_a_scan_that_recorded_mail_wakes_the_ingest_and_queues_the_next_scan(self):
        self.run_job()

        self.assertEqual(ingest_runs().get().payload, {"requested": "inbound"})
        job = intake_jobs().get()
        self.assertAlmostEqual((job.available_at - timezone.now()).total_seconds(), 120, delta=5)

    def test_a_quiet_scan_wakes_nothing_and_a_waiting_scan_gets_no_successor(self):
        self.run_job(FakeReader([], {}))
        self.assertFalse(ingest_runs().exists())
        self.assertEqual(intake_jobs().count(), 1)

        self.run_job(FakeReader([], {}))
        self.assertEqual(intake_jobs().count(), 1)

    def test_a_scan_that_fails_unexpectedly_still_queues_the_next(self):
        with patch("apps.helpdesk.services.intake.scanner.scan_inbox", side_effect=RuntimeError("gone")):
            with self.assertRaises(RuntimeError):
                jobs.run_intake_job(job=None)

        self.assertEqual(intake_jobs().count(), 1)

    def test_switched_off_nothing_is_queued(self):
        HelpdeskSettings.objects.create(enabled=False)

        self.run_job()

        self.assertFalse(jobs.ensure_scheduled())
        self.assertFalse(jobs.run_now())
        self.assertFalse(intake_jobs().exists())
        self.assertFalse(InboundMessage.objects.exists())

    def test_maintenance_queues_one_scan_and_scan_now_queues_one_at_once(self):
        self.assertTrue(jobs.ensure_scheduled())
        self.assertFalse(jobs.ensure_scheduled())
        intake_jobs().update(status=BackgroundJob.Status.PROCESSING)
        self.assertFalse(jobs.ensure_scheduled())

        self.assertTrue(jobs.run_now())
        self.assertEqual(intake_jobs().filter(payload={"requested": "manual"}).count(), 1)

    def test_the_worker_runs_the_whole_pipeline_from_inbox_to_tickets(self):
        bodies = {"human-1": corpus.message(message_id="<q1@example.org>", subject="Question")}
        reader = FakeReader(self.messages[1:2], bodies)
        reader.mailbox = SITE
        jobs.run_now()

        with patch(READER, return_value=(reader, SITE, "")), patch(INGEST_READER, return_value=(reader, SITE, "")):
            for _cycle in range(2):
                for job in claim_jobs():
                    run_claimed_job(job)

        self.assertEqual(InboundMessage.objects.get().status, Status.DONE)
        self.assertEqual(Ticket.objects.get().subject, "Question")
        self.assertEqual(reader.opened, ["human-1"])

    def test_finished_scan_jobs_older_than_a_week_are_purged(self):
        old, recent = timezone.now() - timedelta(days=8), timezone.now() - timedelta(days=1)
        for completed in (old, recent):
            BackgroundJob.objects.create(
                kind=jobs.INTAKE_JOB_KIND, dedupe_key=str(completed), status="succeeded", completed_at=completed
            )

        self.assertEqual(jobs.purge_finished_jobs(), 1)
        self.assertEqual(intake_jobs().count(), 1)


class StatusTests(IntakeTestCase):
    def describe(self, reader=True):
        with patch(STATUS_READER, return_value=(self.reader if reader else None, SITE, "")):
            return status.describe()

    def card(self, reader=True, problem=""):
        with patch(STATUS_READER, return_value=(self.reader if reader else None, SITE, problem)):
            return status.card(now=self.now)

    def test_the_email_monitoring_card_sees_the_intake_as_it_is(self):
        url = "/admin/helpdesk/helpdesksettings/#helpdesk-intake"
        self.assertEqual(self.describe(), InboxReader("Helpdesk intake", "running", 120, url))
        intake_state.set_paused(SITE, True)
        self.assertEqual(self.describe().state, "paused")
        self.assertEqual(self.describe(reader=False).state, "inactive")
        HelpdeskSettings.objects.create(enabled=False)
        self.assertEqual(self.describe().state, "off")

    def test_the_card_level_follows_the_state(self):
        self.assertEqual(self.card()["level"], "waiting")
        intake_state.set_paused(SITE, True)
        self.assertEqual(self.card()["level"], "paused")  # paused before its first scan reads as paused
        intake_state.set_paused(SITE, False)
        IntakeState.objects.filter(mailbox=SITE).update(
            last_run_finished_at=self.ago(minutes=1), last_success_at=self.ago(minutes=1)
        )
        self.assertEqual(self.card()["level"], "ok")
        IntakeState.objects.filter(mailbox=SITE).update(last_success_at=self.ago(minutes=7))
        self.assertEqual(self.card()["level"], "warning")
        IntakeState.objects.filter(mailbox=SITE).update(consecutive_failures=2)
        self.assertEqual(self.card()["level"], "error")
        self.assertEqual(self.card(reader=False, problem="No read scope.")["level"], "inactive")
        HelpdeskSettings.objects.create(enabled=False)
        self.assertEqual(self.card()["level"], "off")

    def test_the_card_counts_waiting_mail_and_shows_the_next_scan_and_cadence(self):
        self.scan()
        InboundMessage.objects.filter(graph_id="ndr-1").update(status=Status.DONE)
        jobs.ensure_scheduled(now=self.now + timedelta(minutes=2))

        card = self.card()

        self.assertEqual((card["waiting"], card["every"], card["catch_up"]), (2, "2 min", "30 s"))
        self.assertEqual(card["next_scan_at"], self.now + timedelta(minutes=2))
        self.assertFalse(card["scan_running"])
        self.assertEqual(card["url"], "/admin/helpdesk/helpdesksettings/intake/")
        with monitoring_settings(inbox_scan_interval_seconds=30):
            self.assertEqual(status.cadence(), {"every": "1 min", "catch_up": "30 s"})
        with patch(STATUS_READER, return_value=(None, "", "Microsoft Graph is not configured.")):
            self.assertEqual((status.card()["waiting"], status.card()["state"]), (0, None))
