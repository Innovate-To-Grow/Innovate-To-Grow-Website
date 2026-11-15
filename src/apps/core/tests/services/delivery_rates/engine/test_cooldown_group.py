from datetime import timedelta
from decimal import Decimal

from apps.core.services import delivery_rates as rates
from apps.core.tests.services.delivery_rates.engine.test_limiter import MAILBOX, LimiterTestCase, state_of

from ..helpers import Channel, set_policy


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
