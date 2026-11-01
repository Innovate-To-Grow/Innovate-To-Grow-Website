"""The limiter on real state rows: admission waits or defers, the bulk lane, Smart rate switches, the transaction
guard, cooldown groups, AIMD feedback, release and ``controlled``."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase

from apps.core.models import DeliveryRatePolicy, DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.runtime import context
from apps.core.services.delivery_rates.runtime import state as state_module

from .helpers import START, Channel, FakeClock, set_policy

MAILBOX = "i2g@example.edu"
SMART = DeliveryRateState.Mode.SMART


def state_of(channel=Channel.GRAPH_SEND, identity=MAILBOX):
    return DeliveryRateState.objects.get(channel=channel, identity=identity)


class LimiterTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)

    def admit(self, channel=Channel.GRAPH_SEND, identity=MAILBOX, **options):
        return rates.admit(channel, identity, **options)


class AdmissionTests(LimiterTestCase):
    def test_the_first_request_goes_out_at_once_and_creates_the_state(self):
        admission = self.admit(budget_cost=2, message_cost=1)

        state = state_of()
        self.assertEqual(admission.send_at, START)
        self.assertEqual(admission.wait_seconds, 0)
        self.assertEqual((state.cooldown_group, state.mode), (f"graph:{MAILBOX}", SMART))
        self.assertEqual(state.usage_buckets.get().total, 2)
        self.assertEqual(self.clock.slept, [])

    def test_manual_30_per_minute_spaces_requests_two_seconds_apart(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))
        sends = [self.admit().send_at for _ in range(4)]

        gaps = [(later - earlier).total_seconds() for earlier, later in zip(sends, sends[1:], strict=False)]
        self.assertEqual(gaps, [2.0, 2.0, 2.0])
        self.assertEqual(self.clock.slept, [2.0, 2.0, 2.0])

    def test_a_request_that_would_wait_too_long_is_deferred_without_taking_a_slot(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(1))
        for _ in range(3):  # the burst of 3 fits: 1/min is far below the 30/min limit
            self.admit()
        tat = state_of().tat

        with self.assertRaises(rates.RateDeferred) as caught:
            self.admit(max_wait=10)

        deferred = caught.exception
        self.assertEqual((deferred.reason, deferred.retry_after), ("pace", 60))
        state = state_of()
        self.assertEqual(state.tat, tat)
        self.assertEqual(state.all_gate_until, deferred.until)

    def test_the_wait_cap_follows_the_wait_mode(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(2))  # one per 30 s
        for _ in range(3):
            self.admit()

        with rates.wait_mode(rates.WaitMode.INLINE), self.assertRaises(rates.RateDeferred):
            self.admit()
        with rates.wait_mode(rates.WaitMode.WORKER):
            admission = self.admit()

        self.assertEqual(admission.wait_seconds, 30)

    def test_an_unknown_channel_or_a_too_long_identity_is_refused(self):
        with self.assertRaises(ValueError):
            rates.admit("fax_send", MAILBOX)
        with self.assertRaises(ValueError):
            self.admit(identity="x" * 600)


class BulkLaneTests(LimiterTestCase):
    def setUp(self):
        super().setUp()
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))  # 2 s; bulk 2.5 s

    def test_a_worker_defers_a_campaign_more_than_one_bulk_interval_away(self):
        # Without the clock moving, the third campaign slot is two bulk intervals (5 s) away.
        with rates.wait_mode(rates.WaitMode.WORKER), patch.object(context, "sleep"):
            self.admit(lane=rates.Lane.BULK)
            self.admit(lane=rates.Lane.BULK)  # 2.5 s: within one bulk interval
            with self.assertRaises(rates.RateDeferred) as caught:
                self.admit(lane=rates.Lane.BULK)

        self.assertEqual(caught.exception.until, START + timedelta(seconds=5))
        self.assertEqual(state_of().bulk_gate_until, caught.exception.until)

    def test_a_worker_defers_a_campaign_during_a_cooldown_it_could_wait_out(self):
        rates.record(self.admit(), rates.throttle(retry_after=20))

        with rates.wait_mode(rates.WaitMode.WORKER), self.assertRaises(rates.RateDeferred) as caught:
            self.admit(lane=rates.Lane.BULK)

        self.assertEqual(caught.exception.reason, "cooldown")
        self.assertEqual(self.clock.slept, [])

    def test_transactional_mail_is_not_queued_behind_campaign_slots(self):
        with rates.wait_mode(rates.WaitMode.WORKER):
            self.admit(lane=rates.Lane.BULK)
            self.admit(lane=rates.Lane.BULK)
            admission = self.admit()

        self.assertLessEqual(admission.wait_seconds, 2.5)

    def test_a_dedicated_thread_waits_its_turn_instead_of_deferring(self):
        with rates.wait_mode(rates.WaitMode.DEDICATED):
            sends = [self.admit(lane=rates.Lane.BULK).send_at for _ in range(5)]

        gaps = [(later - earlier).total_seconds() for earlier, later in zip(sends, sends[1:], strict=False)]
        self.assertEqual(gaps, [2.5, 2.5, 2.5, 2.5])


class SmartRateSwitchTests(LimiterTestCase):
    def test_switches_reset_the_factor_keep_the_cooldown_and_never_change_the_manual_rate(self):
        admission = self.admit()
        rates.record(admission, rates.throttle(retry_after=600))
        cut = state_of()
        self.assertEqual(cut.factor_base, 0.5)

        for smart in (False, True, False, True):
            set_policy(Channel.GRAPH_SEND, smart_enabled=smart)
            with self.assertRaises(rates.RateDeferred):
                self.admit(max_wait=0)

        state = state_of()
        self.assertEqual((state.mode, state.factor_base), (SMART, 1.0))
        self.assertEqual(state.cooldown_until, cut.cooldown_until)
        self.assertEqual(DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND).manual_rate, Decimal("24.000"))

    def test_reset_smart_rate_starts_afresh_on_the_next_request(self):
        rates.record(self.admit(), rates.throttle(retry_after=1))
        self.clock.advance(2)

        self.assertEqual(rates.reset_smart(Channel.GRAPH_SEND), 1)
        self.admit()

        self.assertEqual(state_of().factor_base, 1.0)


class TransactionGuardTests(LimiterTestCase):
    def test_admission_inside_a_callers_transaction_raises_in_tests(self):
        with self.assertRaises(rates.AdmissionInTransaction), transaction.atomic():
            self.admit()

    def test_production_only_warns(self):
        with (
            patch.object(state_module, "_strict", return_value=False),
            self.assertLogs(state_module.logger, "WARNING"),
            transaction.atomic(),
        ):
            admission = self.admit()

        self.assertIsNotNone(admission)


class CooldownGroupTests(LimiterTestCase):
    def test_a_graph_read_throttle_also_stops_graph_sends_of_the_mailbox(self):
        self.admit()  # graph_send has a state already
        read = self.admit(Channel.GRAPH_READ)

        rates.record(read, rates.throttle(retry_after=20))

        with self.assertRaises(rates.RateDeferred) as caught:
            self.admit(max_wait=5)
        self.assertEqual(caught.exception.reason, "cooldown")
        self.assertEqual(state_of().cooldown_until, self.clock.now() + timedelta(seconds=20))

    def test_a_new_identity_starts_inside_its_groups_cooldown(self):
        rates.record(self.admit(Channel.GRAPH_READ), rates.throttle(retry_after=20))

        admission = self.admit(max_wait=30)

        self.assertEqual(admission.wait_seconds, 20)

    def test_other_mailboxes_are_not_affected(self):
        rates.record(self.admit(Channel.GRAPH_READ), rates.throttle(retry_after=20))

        self.assertEqual(self.admit(identity="other@example.edu").wait_seconds, 0)


class FeedbackTests(LimiterTestCase):
    def test_three_in_flight_throttles_cut_once(self):
        admissions = [self.admit() for _ in range(3)]
        for admission in admissions:
            self.clock.advance(1)
            rates.record(admission, rates.throttle(retry_after=1))

        state = state_of()
        self.assertEqual((state.factor_base, state.consecutive_throttles), (0.5, 3))

    def test_recovery_adds_a_step_per_interval_after_a_cut(self):
        rates.record(self.admit(), rates.throttle(retry_after=1))
        self.clock.advance(600)
        admission = self.admit()
        rates.record(admission, rates.ok())

        status = rates.channel_status(Channel.GRAPH_SEND, now=self.clock.now())
        self.assertAlmostEqual(status.identities[0].rate.factor, 0.6)
        self.assertEqual(state_of().consecutive_throttles, 0)

    def test_manual_rate_never_slows_down_but_still_honours_retry_after(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))
        rates.record(self.admit(), rates.throttle(retry_after=15))

        state = state_of()
        self.assertEqual(state.factor_base, 1.0)
        self.assertEqual(self.admit(max_wait=20).wait_seconds, 15)

    def test_uncertain_outcomes_give_no_recovery_credit(self):
        rates.record(self.admit(), rates.throttle(retry_after=1))
        self.clock.advance(599)
        rates.record(self.admit(), rates.uncertain())
        self.clock.advance(599)

        status = rates.channel_status(Channel.GRAPH_SEND, now=self.clock.now())
        self.assertAlmostEqual(status.identities[0].rate.factor, 0.5)

    def test_persistent_throttling_opens_the_breaker(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))
        for _ in range(8):
            admission = self.admit(max_wait=3_600)
            rates.record(admission, rates.throttle(retry_after=1))

        state = state_of()
        self.assertEqual((state.breaker_state, state.breaker_reason), ("open", "persistent_throttle"))
        with self.assertRaises(rates.RateDeferred) as caught:
            self.admit(max_wait=0)
        self.assertEqual(caught.exception.reason, "breaker:persistent_throttle")

    def test_record_and_release_settle_an_admission_once(self):
        admission = self.admit(budget_cost=1)
        rates.record(admission, rates.ok())
        rates.release(admission)
        rates.record(admission, rates.throttle(retry_after=60))

        state = state_of()
        self.assertIsNone(state.cooldown_until)
        self.assertEqual(state.usage_buckets.get().total, 1)


class ReleaseTests(LimiterTestCase):
    def test_release_gives_back_the_slot_and_the_budget(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))
        first = self.admit()
        second = self.admit(budget_cost=3)

        rates.release(second)

        state = state_of()
        self.assertEqual(state.tat, first.tat_after)
        self.assertEqual(state.usage_buckets.get().total, 0)

    def test_release_keeps_the_slot_when_a_later_request_took_one(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(30))
        first = self.admit()
        later = self.admit()

        rates.release(first)

        self.assertEqual(state_of().tat, later.tat_after)


class ControlledTests(LimiterTestCase):
    def test_a_clean_block_records_ok(self):
        with rates.controlled(Channel.GRAPH_READ, MAILBOX) as admission:
            pass

        self.assertTrue(admission.settled)
        self.assertEqual(state_of(Channel.GRAPH_READ).last_signal, "ok")

    def test_the_block_can_report_its_own_signal(self):
        with rates.controlled(Channel.GRAPH_READ, MAILBOX) as admission:
            admission.signal = rates.throttle(retry_after=9)

        self.assertEqual(state_of(Channel.GRAPH_READ).last_signal, "throttle")

    def test_an_exception_is_classified_and_reraised(self):
        with (
            self.assertRaises(TimeoutError),
            rates.controlled(Channel.GRAPH_READ, MAILBOX, classify=lambda exc: rates.throttle(retry_after=3)),
        ):
            raise TimeoutError

        self.assertEqual(state_of(Channel.GRAPH_READ).last_signal, "throttle")

    def test_an_unclassified_exception_counts_as_uncertain(self):
        with self.assertRaises(RuntimeError), rates.controlled(Channel.GRAPH_READ, MAILBOX):
            raise RuntimeError

        self.assertEqual(state_of(Channel.GRAPH_READ).last_signal, "uncertain")
