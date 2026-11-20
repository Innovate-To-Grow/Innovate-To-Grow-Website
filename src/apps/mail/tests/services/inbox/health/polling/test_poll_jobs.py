"""``inbox.polling``: the background job chain that runs the poll."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import registered_job_kinds
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.polling import poller as polling
from apps.mail.services.inbox.reading.connection import InboxError


class PollJobTests(TestCase):
    def jobs(self):
        return BackgroundJob.objects.filter(kind=polling.POLL_JOB_KIND)

    def test_the_kind_is_registered(self):
        self.assertEqual(
            registered_job_kinds()[polling.POLL_JOB_KIND].handler,
            "apps.mail.services.inbox.polling.poller.run_poll_job",
        )

    def test_maintenance_queues_one_poll(self):
        self.assertTrue(polling.ensure_scheduled())
        self.assertFalse(polling.ensure_scheduled())

        job = self.jobs().get()
        self.assertEqual((job.status, job.max_attempts, job.payload), ("pending", 1, {"requested": "scheduled"}))

    def test_a_running_or_retrying_poll_counts_as_scheduled(self):
        for status in (BackgroundJob.Status.PROCESSING, BackgroundJob.Status.RETRY):
            with self.subTest(status=status):
                BackgroundJob.objects.all().delete()
                BackgroundJob.objects.create(kind=polling.POLL_JOB_KIND, dedupe_key="running", status=status)

                self.assertFalse(polling.ensure_scheduled())
                self.assertEqual(self.jobs().count(), 1)

    def test_a_finished_poll_does_not_count(self):
        BackgroundJob.objects.create(kind=polling.POLL_JOB_KIND, dedupe_key="done", status="succeeded")

        self.assertTrue(polling.ensure_scheduled())
        self.assertEqual(self.jobs().filter(status="pending").count(), 1)

    @override_settings(MAIL_INBOX_POLL_SECONDS=0)
    def test_switched_off_nothing_is_queued(self):
        self.assertFalse(polling.enabled())
        self.assertFalse(polling.ensure_scheduled())
        with patch.object(polling, "poll_accounts") as poll:
            polling.run_poll_job(job=None)

        poll.assert_called_once_with()
        self.assertFalse(self.jobs().exists())

    def test_a_poll_queues_the_next_one_an_interval_later(self):
        before = timezone.now()
        with patch.object(polling, "poll_accounts", return_value={}):
            polling.run_poll_job(job=None)

        job = self.jobs().get()
        self.assertGreaterEqual(job.available_at, before + timedelta(seconds=health.poll_interval_seconds()))
        self.assertLessEqual(job.available_at, timezone.now() + timedelta(seconds=health.poll_interval_seconds()))

    @override_settings(MAIL_INBOX_POLL_SECONDS=600)
    def test_the_next_poll_follows_the_setting(self):
        before = timezone.now()
        with patch.object(polling, "poll_accounts", return_value={}):
            polling.run_poll_job(job=None)

        self.assertGreaterEqual(self.jobs().get().available_at, before + timedelta(seconds=600))

    def test_a_failing_poll_still_queues_the_next_one(self):
        with patch.object(polling, "poll_accounts", side_effect=InboxError("no tables")), self.assertRaises(InboxError):
            polling.run_poll_job(job=None)

        self.assertEqual(self.jobs().filter(status="pending").count(), 1)

    def test_no_second_poll_is_queued_while_one_waits(self):
        polling.ensure_scheduled()
        with patch.object(polling, "poll_accounts", return_value={}):
            polling.run_poll_job(job=None)

        self.assertEqual(self.jobs().count(), 1)

    def test_finished_polls_older_than_a_day_are_purged(self):
        now = timezone.now()
        old, recent = now - timedelta(days=1, minutes=1), now - timedelta(hours=23)
        for index, (status, completed) in enumerate(
            (("succeeded", old), ("failed", old), ("cancelled", old), ("succeeded", recent), ("pending", None))
        ):
            BackgroundJob.objects.create(
                kind=polling.POLL_JOB_KIND, dedupe_key=f"job-{index}", status=status, completed_at=completed
            )
        BackgroundJob.objects.create(kind="other.kind", dedupe_key="other", status="succeeded", completed_at=old)

        self.assertEqual(polling.purge_finished_jobs(now=now), 3)
        self.assertEqual(sorted(self.jobs().values_list("dedupe_key", flat=True)), ["job-3", "job-4"])
        self.assertTrue(BackgroundJob.objects.filter(kind="other.kind").exists())
