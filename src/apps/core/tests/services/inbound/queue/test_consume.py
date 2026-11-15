from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import InboundMessage
from apps.core.services.email.inbound import (
    consume,
    purge_expired,
)
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.core.tests.services.inbound.queue.test_queue import Status, row


class ConsumeTests(TestCase):
    def test_claims_the_oldest_due_row_and_counts_the_attempt(self):
        now = timezone.now()
        newer = row(received_at=now - timedelta(minutes=1))
        older = row(received_at=now - timedelta(minutes=5))
        row(received_at=now - timedelta(minutes=9), next_attempt_at=now + timedelta(minutes=5))

        claimed = consume.claim_next(now=now)

        self.assertEqual(claimed.pk, older.pk)
        self.assertEqual((claimed.status, claimed.attempts), (Status.PROCESSING, 1))
        self.assertEqual(consume.claim_next(now=now).pk, newer.pk)
        self.assertIsNone(consume.claim_next(now=now))

    def test_next_due_at(self):
        now = timezone.now()
        self.assertIsNone(consume.next_due_at(now=now))
        later = row(next_attempt_at=now + timedelta(minutes=5))
        self.assertEqual(consume.next_due_at(now=now), later.next_attempt_at)
        row()
        self.assertEqual(consume.next_due_at(now=now), now)

    def test_done_records_what_became_of_it(self):
        row()
        claimed = consume.claim_next()

        consume.done(claimed, classification="human", subtype="", result={"ticket": 1001})

        claimed.refresh_from_db()
        self.assertEqual(
            (claimed.status, claimed.classification, claimed.result), (Status.DONE, "human", {"ticket": 1001})
        )
        self.assertIsNotNone(claimed.processed_at)

    def test_failures_back_off_then_fail_for_staff(self):
        row()
        now = timezone.now()
        for attempt in (1, 2):
            claimed = consume.claim_next(now=now)
            self.assertFalse(consume.retry(claimed, "Microsoft Graph could not be reached.", max_attempts=3, now=now))
            claimed.refresh_from_db()
            self.assertEqual(claimed.status, Status.PENDING)
            self.assertEqual(
                claimed.next_attempt_at, now + timedelta(seconds=consume.RETRY_BASE_SECONDS * 2 ** (attempt - 1))
            )
            now = claimed.next_attempt_at

        claimed = consume.claim_next(now=now)
        self.assertTrue(consume.retry(claimed, "Refused: Bearer abc.def", max_attempts=3, now=now))

        claimed.refresh_from_db()
        self.assertEqual((claimed.status, claimed.attempts), (Status.FAILED, 3))
        self.assertEqual(claimed.last_error, "Refused: [redacted]")

    def test_defer_gives_the_attempt_back(self):
        row()
        claimed = consume.claim_next()
        until = timezone.now() + timedelta(minutes=2)

        consume.defer(claimed, until)

        claimed.refresh_from_db()
        self.assertEqual((claimed.status, claimed.attempts, claimed.next_attempt_at), (Status.PENDING, 0, until))

    def test_skip_and_requeue(self):
        row()
        claimed = consume.claim_next()
        consume.skip(claimed, "No longer in the mailbox.", result={"missing": True})
        done = row(status=Status.DONE)

        claimed.refresh_from_db()
        self.assertEqual((claimed.status, claimed.last_error), (Status.SKIPPED, "No longer in the mailbox."))

        self.assertEqual(consume.requeue(InboundMessage.objects.all()), 1)
        claimed.refresh_from_db()
        done.refresh_from_db()
        self.assertEqual((claimed.status, claimed.attempts, claimed.last_error), (Status.PENDING, 0, ""))
        self.assertEqual(done.status, Status.DONE)

    def test_a_settled_row_is_not_settled_again(self):
        row()
        claimed = consume.claim_next()
        consume.done(claimed)

        consume.skip(claimed, "late")

        claimed.refresh_from_db()
        self.assertEqual(claimed.status, Status.DONE)

    def test_a_row_left_processing_by_a_stopped_worker_returns_to_the_queue(self):
        stale = row(status=Status.PROCESSING)
        InboundMessage.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        fresh = row(status=Status.PROCESSING)

        self.assertEqual(consume.recover_stale(stale_after=timedelta(minutes=15)), 1)

        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual((stale.status, fresh.status), (Status.PENDING, Status.PROCESSING))

    def test_a_row_that_stopped_the_worker_on_every_attempt_fails_for_staff(self):
        # Otherwise a message that kills the worker would be read again, and stop it again, every 15 minutes forever.
        poison = row(status=Status.PROCESSING, attempts=5)
        retried = row(status=Status.PROCESSING, attempts=4)
        InboundMessage.objects.update(updated_at=timezone.now() - timedelta(hours=1))

        self.assertEqual(consume.recover_stale(stale_after=timedelta(minutes=15), max_attempts=5), 2)

        poison.refresh_from_db()
        retried.refresh_from_db()
        self.assertEqual((poison.status, poison.last_error), (Status.FAILED, consume.STOPPED_MID_MESSAGE))
        self.assertIsNotNone(poison.processed_at)
        self.assertEqual(retried.status, Status.PENDING)


class RetentionTests(TestCase):
    def test_rows_go_retention_days_after_processing_or_recording(self):
        now = timezone.now()
        old = now - timedelta(days=91)
        processed_long_ago = row(status=Status.DONE, received_at=old, processed_at=old)
        never_processed = row(received_at=old)
        InboundMessage.objects.filter(pk=never_processed.pk).update(created_at=old)
        processed_recently = row(status=Status.DONE, received_at=old, processed_at=now - timedelta(days=1))
        recent = row(received_at=now)
        in_flight = row(status=Status.PROCESSING, received_at=old)
        InboundMessage.objects.filter(pk=in_flight.pk).update(created_at=old)
        # Old mail recorded just now (a "Rescan since" far back) still waits for its consumer.
        rescanned = row(received_at=old)

        with monitoring_settings(inbound_retention_days=90, purge_batch_size=1):
            self.assertEqual(purge_expired(now=now), 2)

        remaining = set(InboundMessage.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {processed_recently.pk, recent.pk, in_flight.pk, rescanned.pk})
        self.assertNotIn(processed_long_ago.pk, remaining)
        self.assertNotIn(never_processed.pk, remaining)

    def test_a_stop_request_ends_the_purge(self):
        row(received_at=timezone.now() - timedelta(days=200))

        self.assertEqual(purge_expired(should_stop=lambda: True), 0)
        self.assertEqual(InboundMessage.objects.count(), 1)
