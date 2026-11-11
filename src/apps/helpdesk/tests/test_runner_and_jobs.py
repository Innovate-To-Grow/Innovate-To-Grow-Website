"""The ingest run (budgets, Microsoft's throttling, messages gone from the mailbox, failures retried then listed for
staff) and its background job (registration, the chain of runs, pausing while a campaign sends, the hourly restart).
Microsoft Graph is never contacted: the reader is a fake."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob, InboundMessage
from apps.core.services.background_jobs import claim_jobs, registered_job_kinds, run_claimed_job
from apps.core.services.email.graph.mailbox import GraphMessageNotFound, GraphReadBusy, GraphReadError
from apps.core.services.email.inbound import notify_consumers
from apps.mail.models import EmailCampaign

from ..models import HelpdeskSettings, Ticket
from ..services.ingest import jobs, runner
from . import corpus
from .helpers import FakeReader, graph_reader, ingest, queue

Status = InboundMessage.Status


def ingest_jobs():
    return BackgroundJob.objects.filter(kind=jobs.INGEST_JOB_KIND)


class RunnerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()

    def test_a_run_imports_every_due_message_oldest_first(self):
        now = timezone.now()
        newer = queue(
            corpus.message(message_id="<b@x>", subject="Second"),
            reader=self.reader,
            received=now - timedelta(minutes=1),
        )
        older = queue(
            corpus.message(message_id="<a@x>", subject="First"), reader=self.reader, received=now - timedelta(minutes=9)
        )

        outcome = ingest(self.reader)

        self.assertEqual((outcome.stopped, outcome.processed, outcome.tickets, outcome.failed), ("empty", 2, 2, 0))
        self.assertEqual([graph_id for graph_id, _limit in self.reader.fetched], [older.graph_id, newer.graph_id])
        self.assertEqual(list(Ticket.objects.order_by("number").values_list("subject", flat=True)), ["First", "Second"])

    def test_the_read_limit_is_the_smaller_of_the_setting_and_graphs_own(self):
        queue(corpus.message(), reader=self.reader)
        ingest(self.reader, HelpdeskSettings(message_max_bytes=128 * 1024))

        self.assertEqual(self.reader.fetched[0][1], 128 * 1024)

    def test_a_message_larger_than_the_limit_keeps_what_was_read(self):
        raw = corpus.message(
            text="Long text " * 200, attachments=[("a.pdf", b"%PDF-" + b"x" * 90000, "application/pdf")]
        )
        row = queue(raw, reader=self.reader)

        ingest(self.reader, HelpdeskSettings(message_max_bytes=64 * 1024))

        row.refresh_from_db()
        message = Ticket.objects.get(number=row.result["ticket"]).messages.get()
        self.assertTrue(message.body_truncated)
        self.assertIn("Long text", message.body_text)
        self.assertFalse(message.attachments.filter(content__isnull=False).exists())

    def test_a_message_gone_from_the_mailbox_is_skipped_with_the_reason(self):
        row = queue(graph_id="gone")
        self.reader.errors["gone"] = GraphMessageNotFound("Message not found.")

        ingest(self.reader)

        row.refresh_from_db()
        self.assertEqual((row.status, row.last_error), (Status.SKIPPED, runner.GONE))

    def test_a_row_of_another_mailbox_is_skipped(self):
        row = queue(corpus.message(), reader=self.reader, mailbox="old@ucmerced.edu")

        ingest(self.reader)

        row.refresh_from_db()
        self.assertEqual((row.status, row.last_error), (Status.SKIPPED, runner.OTHER_MAILBOX))
        self.assertEqual(self.reader.fetched, [])

    def test_read_failures_retry_and_end_under_ingest_problems(self):
        row = queue(graph_id="flaky")
        self.reader.errors["flaky"] = GraphReadError("Microsoft Graph could not be reached.")
        settings = HelpdeskSettings(max_attempts=2)

        first = ingest(self.reader, settings)
        row.refresh_from_db()
        self.assertEqual((first.failed, row.status, row.attempts), (0, Status.PENDING, 1))
        self.assertIsNotNone(row.next_attempt_at)

        InboundMessage.objects.filter(pk=row.pk).update(next_attempt_at=None)
        second = ingest(self.reader, settings)
        row.refresh_from_db()
        self.assertEqual((second.failed, row.status, row.attempts), (1, Status.FAILED, 2))
        self.assertEqual(row.last_error, "Microsoft Graph could not be reached.")

    def test_a_message_that_cannot_be_processed_is_retried_with_a_generic_error(self):
        row = queue(corpus.message(), reader=self.reader)

        with (
            patch("apps.helpdesk.services.ingest.runner.store", side_effect=ValueError("secret detail")),
            self.assertLogs("apps.helpdesk.services.ingest.runner", level="ERROR") as logs,
        ):
            ingest(self.reader)

        row.refresh_from_db()
        self.assertEqual((row.status, row.last_error), (Status.PENDING, "Could not be imported (ValueError)."))
        self.assertFalse(Ticket.objects.exists())
        # The log names the type and where it was raised, never the text (it can quote the message) or a traceback.
        (record,) = logs.records
        self.assertIn("ValueError at unittest.mock:", record.getMessage())
        self.assertNotIn("secret detail", record.getMessage())
        self.assertIsNone(record.exc_info)

    def test_microsofts_throttle_ends_the_run_and_refunds_the_attempt(self):
        busy = queue(graph_id="busy", received=timezone.now() - timedelta(minutes=9))
        later = queue(corpus.message(), reader=self.reader)
        self.reader.errors["busy"] = GraphReadBusy(90)

        outcome = ingest(self.reader)

        busy.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(outcome.stopped, "busy")
        self.assertAlmostEqual((outcome.busy_until - timezone.now()).total_seconds(), 90, delta=5)
        self.assertEqual((busy.status, busy.attempts, busy.next_attempt_at), (Status.PENDING, 0, outcome.busy_until))
        self.assertEqual(later.status, Status.PENDING)

    def test_the_message_and_time_budgets_end_a_run(self):
        for index in range(3):
            queue(corpus.message(message_id=f"<{index}@x>"), reader=self.reader)

        by_count = ingest(self.reader, HelpdeskSettings(ingest_batch_size=2))
        self.assertEqual((by_count.stopped, by_count.processed), ("budget", 2))

        with patch("apps.helpdesk.services.ingest.runner.time.monotonic", side_effect=[0.0, 1000.0]):
            by_time = ingest(self.reader, HelpdeskSettings(ingest_max_seconds=5))
        self.assertEqual((by_time.stopped, by_time.processed), ("time", 0))

    def test_nothing_runs_when_switched_off_or_without_a_reader(self):
        queue(corpus.message(), reader=self.reader)

        self.assertEqual(runner.run(HelpdeskSettings(enabled=False)).stopped, "disabled")
        with graph_reader(None, "Microsoft Graph is not configured."):
            outcome = runner.run(HelpdeskSettings())
        self.assertEqual((outcome.stopped, outcome.problem), ("no_reader", "Microsoft Graph is not configured."))
        self.assertEqual(InboundMessage.objects.get().status, Status.PENDING)

    def test_a_row_left_processing_by_a_stopped_worker_is_imported_again(self):
        row = queue(corpus.message(), reader=self.reader, status=Status.PROCESSING)
        InboundMessage.objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(hours=2))

        ingest(self.reader)

        row.refresh_from_db()
        self.assertEqual(row.status, Status.DONE)

    def test_a_message_that_stopped_the_worker_on_every_attempt_goes_to_ingest_problems(self):
        settings = HelpdeskSettings(max_attempts=3)
        row = queue(corpus.message(), reader=self.reader, status=Status.PROCESSING, attempts=3)
        InboundMessage.objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(hours=2))

        ingest(self.reader, settings)

        row.refresh_from_db()
        self.assertEqual((row.status, self.reader.fetched), (Status.FAILED, []))
        self.assertIn("stopped part-way", row.last_error)


class JobTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()

    def run_job(self):
        with graph_reader(self.reader):
            jobs.run_ingest_job(job=None)

    def test_the_kinds_are_registered_without_a_delivery_lane(self):
        kind = registered_job_kinds()[jobs.INGEST_JOB_KIND]

        self.assertEqual((kind.family, kind.lane), (None, None))
        self.assertTrue(jobs.ingest_enabled())

    def test_a_scan_that_recorded_mail_queues_the_ingest_and_the_worker_runs_it(self):
        queue(corpus.message(), reader=self.reader)
        self.assertEqual(notify_consumers(), 1)

        with graph_reader(self.reader):
            for job in claim_jobs():
                run_claimed_job(job)

        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(ingest_jobs().get().status, BackgroundJob.Status.SUCCEEDED)

    def test_a_run_stopped_by_its_budget_queues_the_next_at_once(self):
        HelpdeskSettings.objects.create(ingest_batch_size=1)
        for index in range(2):
            queue(corpus.message(message_id=f"<{index}@x>"), reader=self.reader)

        self.run_job()

        job = ingest_jobs().get()
        self.assertLessEqual((job.available_at - timezone.now()).total_seconds(), jobs.CONTINUE_SECONDS + 1)

    def test_the_next_run_follows_retries_and_throttles(self):
        now = timezone.now()
        self.assertIsNone(jobs.next_run_at(runner.RunOutcome("empty"), now=now))
        self.assertIsNone(jobs.next_run_at(runner.RunOutcome("no_reader"), now=now))
        busy_until = now + timedelta(minutes=3)
        self.assertEqual(jobs.next_run_at(runner.RunOutcome("busy", busy_until=busy_until), now=now), busy_until)
        retry_at = now + timedelta(minutes=7)
        queue(next_attempt_at=retry_at)
        self.assertEqual(jobs.next_run_at(runner.RunOutcome("empty"), now=now), retry_at)

    def test_while_a_campaign_sends_the_run_waits(self):
        EmailCampaign.objects.create(subject="Blast", status="sending")
        queue(corpus.message(), reader=self.reader)

        self.run_job()
        self.run_job()

        self.assertFalse(Ticket.objects.exists())
        job = ingest_jobs().get()
        self.assertEqual(job.payload, {"requested": "campaign-pause"})
        self.assertGreater(job.available_at, timezone.now() + timedelta(seconds=60))

    def test_the_campaign_pause_can_be_switched_off(self):
        HelpdeskSettings.objects.create(pause_while_campaign_sending=False)
        EmailCampaign.objects.create(subject="Blast", status="sending")
        queue(corpus.message(), reader=self.reader)

        self.run_job()

        self.assertEqual(Ticket.objects.count(), 1)

    def test_switched_off_nothing_runs_or_is_queued(self):
        HelpdeskSettings.objects.create(enabled=False)
        queue(corpus.message(), reader=self.reader)

        self.run_job()

        self.assertFalse(Ticket.objects.exists())
        self.assertFalse(jobs.ensure_scheduled())
        self.assertFalse(ingest_jobs().exists())
        self.assertFalse(jobs.ingest_enabled())

    def test_maintenance_restarts_the_chain_only_when_mail_waits(self):
        self.assertFalse(jobs.ensure_scheduled())
        queue(corpus.message(), reader=self.reader)

        self.assertTrue(jobs.ensure_scheduled())
        self.assertFalse(jobs.ensure_scheduled())
        self.assertEqual(ingest_jobs().count(), 1)

    def test_finished_ingest_jobs_older_than_a_week_are_purged(self):
        old, recent = timezone.now() - timedelta(days=8), timezone.now() - timedelta(days=1)
        for completed in (old, recent):
            BackgroundJob.objects.create(
                kind=jobs.INGEST_JOB_KIND, dedupe_key=str(completed), status="succeeded", completed_at=completed
            )

        self.assertEqual(jobs.purge_finished_jobs(), 1)
        self.assertEqual(ingest_jobs().count(), 1)
