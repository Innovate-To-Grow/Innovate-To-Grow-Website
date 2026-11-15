"""The helpdesk's intake: its own scan of the Inbox (separate from bounce processing), its state (lease, checkpoint,
pause, "Rescan since", first-scan lookback), its background jobs and what the cards show of it. Microsoft Graph is
never contacted: the reader is a fake listing a fixed Inbox."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob, InboundMessage
from apps.core.services.background_jobs import claim_jobs, registered_job_kinds, run_claimed_job
from apps.core.services.email.inbound import registered_inbox_readers
from apps.core.tests.services.email_monitoring.bounce_scan.test_bounce_scanner import FakeReader, listed
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings

from ...models import HelpdeskSettings, IntakeState, Ticket
from ...services.ingest.pipeline import jobs as ingest_jobs
from ...services.intake import jobs, scanner
from .. import corpus
from ..corpus import SITE

READER = "apps.helpdesk.services.intake.scanner.active_reader"
STATUS_READER = "apps.helpdesk.services.intake.status.active_reader"
INGEST_READER = "apps.helpdesk.services.ingest.pipeline.runner.active_reader"
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
