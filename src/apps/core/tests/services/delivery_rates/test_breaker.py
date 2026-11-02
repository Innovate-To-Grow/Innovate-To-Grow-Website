"""Breakers: a stop defers every request without a provider call, a timed probe lets exactly one through, its
answer closes or reopens the breaker, campaigns-only stops let transactional mail pass, and saving a configuration
or "Resume sending" clears them."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import DeliveryRateState, EmailServiceConfig
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.rules.defaults import rate_spec
from apps.core.services.delivery_rates.runtime.breaker import open_breaker

from .helpers import Channel, FakeClock, set_policy

SES = "1:us-west-2"
OPEN = DeliveryRateState.BreakerState.OPEN
CLOSED = DeliveryRateState.BreakerState.CLOSED


def ses_state():
    return DeliveryRateState.objects.get(channel=Channel.SES_SEND, identity=SES)


class BreakerTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)
        set_policy(Channel.SES_SEND, smart_enabled=False, manual_rate=Decimal(10), provider_limit=Decimal(10))

    def admit(self, lane="transactional", max_wait=1):
        return rates.admit(Channel.SES_SEND, SES, lane=lane, budget_cost=1, message_cost=1, max_wait=max_wait)

    def stop(self, signal):
        rates.record(self.admit(), signal)
        return ses_state()


class StopTests(BreakerTestCase):
    def test_account_sending_paused_defers_fifty_requests_with_no_provider_call(self):
        state = self.stop(rates.blocked("account_paused"))
        self.assertEqual((state.breaker_state, state.breaker_scope), (OPEN, "all"))

        deferred = 0
        for _ in range(50):
            try:
                self.admit()
            except rates.RateDeferred as exc:
                deferred += 1
                self.assertEqual(exc.reason, "breaker:account_paused")
        self.assertEqual(deferred, 50)
        self.assertEqual(ses_state().all_gate_until, state.breaker_retry_at)

    def test_the_first_probe_is_due_after_the_controllers_probe_interval(self):
        state = self.stop(rates.blocked("auth"))

        self.assertEqual(state.breaker_retry_at, self.clock.now() + timedelta(seconds=900))

    def test_a_quota_stop_uses_its_own_recheck(self):
        state = self.stop(rates.quota("daily_quota", seconds=600))

        self.assertEqual(state.breaker_interval_seconds, 600)

    def test_requests_already_in_flight_do_not_double_the_interval(self):
        admissions = [self.admit(max_wait=1) for _ in range(3)]
        for admission in admissions:
            rates.record(admission, rates.blocked("auth"))

        self.assertEqual(ses_state().breaker_interval_seconds, 900)


class ProbeTests(BreakerTestCase):
    def setUp(self):
        super().setUp()
        self.stop(rates.blocked("account_paused"))
        self.clock.advance(900)

    def test_half_open_lets_exactly_one_request_through(self):
        probe = self.admit()
        self.assertIsNotNone(probe.probe_id)

        for _ in range(5):
            with self.assertRaises(rates.RateDeferred):
                self.admit()
        self.assertEqual(ses_state().breaker_state, DeliveryRateState.BreakerState.HALF_OPEN)

    def test_the_timed_probe_closes_account_paused_without_any_discovery(self):
        rates.record(self.admit(), rates.ok())

        state = ses_state()
        self.assertEqual((state.breaker_state, state.breaker_reason), (CLOSED, ""))
        self.assertIsNone(state.all_gate_until)
        self.assertIsNotNone(self.admit(max_wait=1))

    def test_a_failed_probe_doubles_the_interval_up_to_the_maximum(self):
        for expected in (1_800, 3_600, 7_200, 14_400, 21_600, 21_600):
            rates.record(self.admit(), rates.blocked("account_paused"))
            state = ses_state()
            self.assertEqual(state.breaker_interval_seconds, expected)
            self.clock.advance(expected)

    def test_an_unclear_probe_reopens_with_the_same_interval(self):
        rates.record(self.admit(), rates.uncertain())

        state = ses_state()
        self.assertEqual((state.breaker_state, state.breaker_interval_seconds), (OPEN, 900))
        self.assertIsNone(state.breaker_probe_id)

    def test_a_probe_that_was_released_lets_the_next_request_probe(self):
        rates.release(self.admit())

        self.assertIsNotNone(self.admit().probe_id)

    def test_a_probe_that_never_reports_is_replaced_after_its_interval(self):
        self.admit()
        self.clock.advance(900)

        self.assertIsNotNone(self.admit().probe_id)


class ScopeTests(BreakerTestCase):
    def test_a_campaigns_only_stop_lets_transactional_mail_through(self):
        self.stop(rates.blocked("sending_paused", scope=rates.Scope.BULK))

        self.assertIsNotNone(self.admit(max_wait=1))
        with self.assertRaises(rates.RateDeferred):
            self.admit(lane="bulk")
        self.assertIsNotNone(ses_state().bulk_gate_until)

    def test_a_later_full_stop_widens_a_campaigns_only_breaker(self):
        self.stop(rates.blocked("sending_paused", scope=rates.Scope.BULK))
        self.stop(rates.blocked("account_paused"))

        self.assertEqual(ses_state().breaker_scope, "all")


class ConfigSaveTests(BreakerTestCase):
    def test_saving_the_config_half_opens_an_auth_breaker(self):
        self.stop(rates.blocked(rates.Reason.AUTH))

        with self.captureOnCommitCallbacks(execute=True):
            EmailServiceConfig.objects.create(name="Mail", from_email="a@example.edu")

        self.assertEqual(ses_state().breaker_retry_at, self.clock.now())
        self.assertIsNotNone(self.admit().probe_id)

    def test_other_stops_wait_for_their_timed_probe(self):
        state = self.stop(rates.blocked("account_paused"))

        with self.captureOnCommitCallbacks(execute=True):
            EmailServiceConfig.objects.create(name="Mail", from_email="a@example.edu")

        self.assertEqual(ses_state().breaker_retry_at, state.breaker_retry_at)


class ResumeTests(BreakerTestCase):
    def test_resume_sending_clears_breakers_and_cooldowns(self):
        self.stop(rates.blocked("account_paused"))
        DeliveryRateState.objects.filter(pk=ses_state().pk).update(
            cooldown_until=self.clock.now() + timedelta(seconds=600),
            cooldown_reason="throttled",
            consecutive_throttles=3,
        )

        self.assertEqual(rates.resume(Channel.SES_SEND), 1)

        state = ses_state()
        self.assertEqual((state.breaker_state, state.cooldown_until, state.consecutive_throttles), (CLOSED, None, 0))
        self.assertIsNotNone(self.admit())


class SpendLimitTests(TestCase):
    def test_the_spend_probe_is_due_at_the_start_of_the_next_month_at_the_latest(self):
        spec = rate_spec(Channel.SMS_SEND)
        state = DeliveryRateState(channel=Channel.SMS_SEND, identity="us-west-2:+15550100", cooldown_group="sms")
        now = datetime(2026, 11, 30, 23, 30, tzinfo=UTC)

        open_breaker(
            state, reason=rates.Reason.SPEND_LIMIT, scope="all", seconds=3_600, spec=spec, now=now, failed_probe=False
        )

        self.assertEqual(state.breaker_retry_at, datetime(2026, 12, 1, tzinfo=UTC))
