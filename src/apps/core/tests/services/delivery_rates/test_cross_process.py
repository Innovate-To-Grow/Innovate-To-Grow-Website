"""Concurrent senders on separate database connections (PostgreSQL only: SQLite has no row locks). Threads stand in
for processes; each uses its own connection."""

import threading
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.test import TransactionTestCase

from apps.core.models import DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.runtime import context

from .helpers import START, Channel, set_policy

MAILBOX = "i2g@example.edu"
WORKERS = 6
# Generous bound for a thread that should not be blocked at all; it only fails a test that would otherwise hang.
THREAD_TIMEOUT_SECONDS = 30


def in_threads(target, count=WORKERS):
    """Run ``target(index)`` in ``count`` threads started together; return results (or exceptions) by index."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def run(index):
        try:
            barrier.wait()
            results[index] = target(index)
        except Exception as exc:  # noqa: BLE001 - the test inspects what each sender got.
            results[index] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(THREAD_TIMEOUT_SECONDS)
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "row locks across connections need PostgreSQL")
class CrossProcessTests(TransactionTestCase):
    def setUp(self):
        # Every thread reads the same fixed clock and never really sleeps.
        for name, value in (("clock", lambda: START), ("sleep", lambda seconds: None)):
            patcher = patch.object(context, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))  # one per 2 s, no burst

    def test_no_two_admissions_share_a_slot(self):
        results = in_threads(lambda index: [rates.admit(Channel.GRAPH_SEND, MAILBOX, max_wait=600) for _ in range(5)])

        slots = sorted(admission.send_at for batch in results for admission in batch)
        self.assertEqual(len(slots), WORKERS * 5)
        gaps = {(later - earlier).total_seconds() for earlier, later in zip(slots, slots[1:], strict=False)}
        self.assertEqual(gaps, {2.0})

    def test_a_graph_read_throttle_on_one_connection_defers_graph_sends_on_another(self):
        rates.admit(Channel.GRAPH_SEND, MAILBOX)
        read = rates.admit(Channel.GRAPH_READ, MAILBOX)

        in_threads(lambda index: rates.record(read, rates.throttle(retry_after=60)), count=1)

        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(Channel.GRAPH_SEND, MAILBOX, max_wait=10)
        self.assertEqual(caught.exception.until, START + timedelta(seconds=60))

    def test_after_a_cooldown_waiting_senders_leave_one_interval_apart(self):
        rates.record(rates.admit(Channel.GRAPH_SEND, MAILBOX), rates.throttle(retry_after=60))

        results = in_threads(lambda index: rates.admit(Channel.GRAPH_SEND, MAILBOX, max_wait=600))

        slots = sorted(admission.send_at for admission in results)
        self.assertEqual(slots[0], START + timedelta(seconds=60))
        self.assertEqual({(b - a).total_seconds() for a, b in zip(slots, slots[1:], strict=False)}, {2.0})

    def test_half_open_lets_exactly_one_of_many_through(self):
        rates.record(rates.admit(Channel.GRAPH_SEND, MAILBOX), rates.blocked("auth"))
        DeliveryRateState.objects.update(breaker_retry_at=START)

        # Each may wait out the pace (2 s), not the breaker's next probe.
        results = in_threads(lambda index: rates.admit(Channel.GRAPH_SEND, MAILBOX, max_wait=5))

        probes = [result for result in results if isinstance(result, rates.Admission)]
        self.assertEqual(len(probes), 1)
        self.assertIsNotNone(probes[0].probe_id)
        self.assertTrue(all(isinstance(result, rates.RateDeferred) for result in results if result not in probes))

    def test_no_lock_is_held_while_a_sender_waits_for_its_slot(self):
        rates.admit(Channel.GRAPH_SEND, MAILBOX)
        waiting, release, sleeps = threading.Event(), threading.Event(), []

        def sleep(seconds):
            # Only the first sender's wait blocks (until the second has been admitted).
            sleeps.append(seconds)
            if len(sleeps) == 1:
                waiting.set()
                release.wait(THREAD_TIMEOUT_SECONDS)

        with patch.object(context, "sleep", sleep):
            first = threading.Thread(
                target=in_threads, args=(lambda index: rates.admit(Channel.GRAPH_SEND, MAILBOX, max_wait=600), 1)
            )
            first.start()
            self.assertTrue(waiting.wait(THREAD_TIMEOUT_SECONDS))
            try:
                # The first sender is asleep before its slot; a held lock would block this one until the timeout.
                second = in_threads(lambda index: rates.admit(Channel.GRAPH_SEND, MAILBOX, max_wait=600), count=1)[0]
            finally:
                release.set()
                first.join(THREAD_TIMEOUT_SECONDS)

        self.assertEqual(second.send_at, START + timedelta(seconds=4))

    def test_admission_inside_a_callers_transaction_raises(self):
        with self.assertRaises(rates.AdmissionInTransaction), transaction.atomic():
            rates.admit(Channel.GRAPH_SEND, MAILBOX)
