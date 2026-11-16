from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, registered_job_kinds, run_claimed_job
from apps.helpdesk.tests.intake.test_runner_and_jobs import ingest_jobs
from apps.mail.models import EmailCampaign

from ...models import HelpdeskSettings, Ticket
from ...services.ingest.pipeline import jobs, runner
from .. import corpus
from ..helpers import FakeReader, graph_reader, queue


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

    def test_an_intake_scan_that_recorded_mail_wakes_the_ingest_and_the_worker_runs_it(self):
        queue(corpus.message(), reader=self.reader)
        self.assertTrue(jobs.wake())

        with graph_reader(self.reader):
            for job in claim_jobs():
                run_claimed_job(job)

        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(ingest_jobs().get().status, BackgroundJob.Status.SUCCEEDED)

    def test_the_wake_up_queues_one_run_while_it_waits_but_a_running_one_does_not_count(self):
        self.assertTrue(jobs.wake())
        self.assertFalse(jobs.wake())
        self.assertEqual(ingest_jobs().get().payload, {"requested": "inbound"})

        # A run in progress may have looked for rows before the new ones were recorded.
        ingest_jobs().update(status=BackgroundJob.Status.PROCESSING)
        self.assertTrue(jobs.wake(now=timezone.now() + timedelta(seconds=1)))
        self.assertEqual(ingest_jobs().count(), 2)

    def test_switched_off_the_wake_up_queues_nothing(self):
        HelpdeskSettings.objects.create(enabled=False)

        self.assertFalse(jobs.wake())
        self.assertFalse(ingest_jobs().exists())

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
        self.assertIsNone(jobs.next_run_at(runner.RunOutcome("paused"), now=now))
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
