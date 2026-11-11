"""The inbound queue: recording listed messages once, waking the registered consumers, the consumer's claim and
settle steps, and retention. No consumer app is involved: the registry is patched where it matters."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import DataError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob, InboundMessage
from apps.core.services.email.inbound import (
    LINK_PLACEHOLDER,
    active_consumer_kinds,
    consume,
    notify_consumers,
    pending_count,
    purge_expired,
    record,
    register_inbound_consumer,
    registered_consumers,
    registry,
)
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings

SITE = "i2g@ucmerced.edu"
Status = InboundMessage.Status
TOKEN = "fake-test-token-0000000000"  # a synthetic value: only its position matters


def listed(graph_id="AAMk-1", **values):
    message = {
        "id": graph_id,
        "subject": f"Re: your link https://i2g.ucmerced.edu/login-link#token={TOKEN}",
        "from": {"emailAddress": {"address": "Pat@Example.org", "name": "Pat Doe"}},
        "internetMessageId": "<m1@example.org>",
        "conversationId": "AAQkADAwATM0MDAAMS1iZjQ2",
    }
    return {**message, **values}


def row(**values):
    defaults = {
        "mailbox": SITE,
        "graph_id": f"AAMk-{InboundMessage.objects.count() + 1}",
        "received_at": timezone.now(),
    }
    return InboundMessage.objects.create(**{**defaults, **values})


class RegistryTests(TestCase):
    def setUp(self):
        self.saved = dict(registry._CONSUMERS)
        self.addCleanup(self.restore)

    def restore(self):
        registry._CONSUMERS.clear()
        registry._CONSUMERS.update(self.saved)

    def test_registering_again_needs_identical_values(self):
        register_inbound_consumer("app.ingest", active="app.on")
        register_inbound_consumer("app.ingest", active="app.on")

        with self.assertRaises(ImproperlyConfigured):
            register_inbound_consumer("app.ingest", active="app.other")
        with self.assertRaises(ImproperlyConfigured):
            register_inbound_consumer("")
        self.assertIn("app.ingest", registered_consumers())

    def test_active_consumers_follow_their_switch_and_a_broken_switch_counts_as_off(self):
        registry._CONSUMERS.clear()
        register_inbound_consumer("always.on")
        register_inbound_consumer("switched.off", active="builtins.bool")
        register_inbound_consumer("broken.switch", active="apps.nowhere.switch")

        with self.assertLogs("apps.core.services.email.inbound.registry", level="ERROR"):
            self.assertEqual(active_consumer_kinds(), ["always.on"])

    def test_the_helpdesk_registers_itself(self):
        self.assertEqual(registered_consumers()["helpdesk.ingest_inbound"].job_kind, "helpdesk.ingest_inbound")


class RecordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.received = timezone.now() - timedelta(minutes=3)

    def test_a_listed_message_is_recorded_once_with_cleaned_metadata(self):
        self.assertTrue(record(SITE, listed(), self.received, candidate=False))
        self.assertFalse(record(SITE, listed(), self.received, candidate=False))

        stored = InboundMessage.objects.get()
        self.assertEqual(
            (stored.mailbox, stored.graph_id, stored.status, stored.kind, stored.folder),
            (SITE, "AAMk-1", Status.PENDING, InboundMessage.Kind.MESSAGE, "inbox"),
        )
        self.assertEqual((stored.from_address, stored.from_name), ("pat@example.org", "Pat Doe"))
        self.assertEqual(stored.subject, f"Re: your link {LINK_PLACEHOLDER}")
        self.assertEqual(
            (stored.internet_message_id, stored.conversation_id), ("<m1@example.org>", "AAQkADAwATM0MDAAMS1iZjQ2")
        )
        self.assertEqual(stored.received_at, self.received)
        self.assertEqual(pending_count(), 1)

    def test_a_bounce_candidate_is_recorded_as_one(self):
        record(SITE, listed(), self.received, candidate=True)

        self.assertEqual(InboundMessage.objects.get().kind, InboundMessage.Kind.BOUNCE_CANDIDATE)

    def test_the_same_graph_id_in_another_mailbox_is_another_message(self):
        record(SITE, listed(), self.received, candidate=False)

        self.assertTrue(record("other@ucmerced.edu", listed(), self.received, candidate=False))

    def test_nothing_is_recorded_without_a_consumer_or_an_id(self):
        with patch("apps.core.services.email.inbound.queue.registered_consumers", return_value={}):
            self.assertFalse(record(SITE, listed(), self.received, candidate=False))
        self.assertFalse(record(SITE, listed(graph_id=""), self.received, candidate=False))
        self.assertFalse(InboundMessage.objects.exists())

    def test_hostile_values_are_bounded(self):
        message = listed(subject="word " * 400, conversationId="C" * 900, internetMessageId="<" + "x" * 300 + ">")
        message["from"] = {"emailAddress": {"address": "not an address", "name": "N\x00" * 400}}

        self.assertTrue(record(SITE, message, self.received, candidate=False))

        stored = InboundMessage.objects.get()
        self.assertEqual((len(stored.subject), len(stored.conversation_id)), (255, 255))
        self.assertEqual((stored.internet_message_id, stored.from_address), ("", ""))
        self.assertNotIn("\x00", stored.from_name)

    def test_a_nul_in_the_message_id_does_not_keep_the_message_out(self):
        # PostgreSQL text cannot hold NUL: kept, it would make the insert fail and the scan move past the message.
        self.assertTrue(record(SITE, listed(internetMessageId="<m1\x00@example.org>"), self.received, candidate=False))

        self.assertEqual(InboundMessage.objects.get().internet_message_id, "<m1@example.org>")

    def test_a_row_recorded_by_another_process_meanwhile_is_not_an_error(self):
        record(SITE, listed(), self.received, candidate=False)
        with patch("apps.core.services.email.inbound.queue.InboundMessage.objects.filter") as lookup:
            lookup.return_value.exists.return_value = False
            self.assertFalse(record(SITE, listed(), self.received, candidate=False))

        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertEqual(str(InboundMessage.objects.get()), f"pat@example.org: Re: your link {LINK_PLACEHOLDER}")
        self.assertEqual(str(InboundMessage(mailbox=SITE)), "unknown sender: (no subject)")

    def test_a_value_the_database_refuses_is_skipped_and_the_scan_goes_on(self):
        with (
            patch.object(InboundMessage.objects, "create", side_effect=DataError("value too long")),
            self.assertLogs("apps.core.services.email.inbound.queue", level="WARNING"),
        ):
            self.assertFalse(record(SITE, listed(), self.received, candidate=False))


class NotifyTests(TestCase):
    def jobs(self):
        return BackgroundJob.objects.filter(kind="helpdesk.ingest_inbound")

    def test_each_active_consumer_is_queued_once_while_its_job_waits(self):
        self.assertEqual(notify_consumers(), 1)
        self.assertEqual(notify_consumers(), 0)

        job = self.jobs().get()
        self.assertEqual((job.status, job.max_attempts), (BackgroundJob.Status.PENDING, 1))

    def test_a_running_consumer_job_does_not_count_as_waiting(self):
        notify_consumers()
        self.jobs().update(status=BackgroundJob.Status.PROCESSING)

        self.assertEqual(notify_consumers(now=timezone.now() + timedelta(seconds=1)), 1)

    def test_a_consumer_that_is_off_is_not_queued(self):
        with patch("apps.core.services.email.inbound.queue.active_consumer_kinds", return_value=[]):
            self.assertEqual(notify_consumers(), 0)
        self.assertFalse(self.jobs().exists())


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
