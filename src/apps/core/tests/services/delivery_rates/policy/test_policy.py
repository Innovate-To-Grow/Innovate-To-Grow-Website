"""The precedence rule (``effective_rate``): Smart rate on ignores the manual rate, Smart rate off returns it
exactly (capped only at a provider limit), last-known reports beat the fallback, and the burst never lets the steady
rate plus the burst exceed the bound."""

from datetime import timedelta

from django.test import SimpleTestCase

from apps.core.models import DeliveryRateState
from apps.core.services.delivery_rates.rules.policy import BoundSource, effective_rate, rate_bound, smart_rate

from ..helpers import START, Channel, policy_for, spec_for, state_for

SMART = DeliveryRateState.Mode.SMART


class SmartRateTakesPriorityTests(SimpleTestCase):
    def test_smart_rate_on_gives_the_same_rate_for_a_manual_rate_of_1_and_1000(self):
        spec = spec_for(Channel.GRAPH_SEND)
        state = state_for(Channel.GRAPH_SEND, mode=SMART, factor_base=1.0, factor_changed_at=START)

        low = effective_rate(policy_for(Channel.GRAPH_SEND, manual_rate=1), state, spec, START)
        high = effective_rate(policy_for(Channel.GRAPH_SEND, manual_rate=1000), state, spec, START)

        self.assertEqual(low.rate, high.rate)
        self.assertAlmostEqual(low.rate, 30 * 0.8)
        self.assertTrue(low.smart)

    def test_smart_rate_is_bound_times_headroom_times_factor(self):
        spec = spec_for(Channel.GRAPH_SEND)
        state = state_for(Channel.GRAPH_SEND, mode=SMART, factor_base=0.5, factor_changed_at=START)

        rate = effective_rate(policy_for(Channel.GRAPH_SEND), state, spec, START)

        self.assertAlmostEqual(rate.rate, 30 * 0.8 * 0.5)
        self.assertEqual(rate.factor, 0.5)

    def test_smart_rate_never_exceeds_the_bound(self):
        for channel in Channel.values:
            with self.subTest(channel=channel):
                spec = spec_for(channel)
                state = state_for(channel, mode=SMART, factor_base=1.0, factor_changed_at=START)
                rate = effective_rate(policy_for(channel), state, spec, START)
                self.assertLessEqual(rate.rate, rate.bound.value)
                if rate.parts:
                    self.assertLessEqual(rate.parts_rate, rate.parts.value)

    def test_a_state_not_yet_in_smart_mode_shows_the_start_factor(self):
        spec = spec_for(Channel.SMTP_SEND)

        rate = effective_rate(policy_for(Channel.SMTP_SEND), state_for(Channel.SMTP_SEND), spec, START)

        # SMTP reports no limit: the fallback (60/min) is only a guess, so Smart rate starts at half of it.
        self.assertEqual(rate.bound.source, BoundSource.FALLBACK)
        self.assertAlmostEqual(rate.rate, 60 * 0.9 * spec.start_factor_without_limit)


class ManualRateTests(SimpleTestCase):
    def test_smart_rate_off_returns_the_manual_rate_exactly(self):
        for channel in Channel.values:
            with self.subTest(channel=channel):
                policy = policy_for(channel, smart_enabled=False)
                rate = effective_rate(policy, state_for(channel), spec_for(channel), START)
                self.assertEqual(rate.rate, float(policy.manual_rate))
                self.assertFalse(rate.manual_capped)
                self.assertIsNone(rate.factor)

    def test_manual_rate_is_capped_at_the_last_known_reported_limit(self):
        policy = policy_for(Channel.SES_SEND, smart_enabled=False, manual_rate=20)
        state = state_for(Channel.SES_SEND, discovered_rate=14.0, discovered_at=START - timedelta(days=3))

        rate = effective_rate(policy, state, spec_for(Channel.SES_SEND), START)

        self.assertEqual(rate.rate, 14.0)
        self.assertTrue(rate.manual_capped)

    def test_manual_rate_is_never_capped_at_the_fallback(self):
        # SMTP's 60/min fallback is the app's guess, not a provider limit.
        policy = policy_for(Channel.SMTP_SEND, smart_enabled=False, manual_rate=100)

        rate = effective_rate(policy, state_for(Channel.SMTP_SEND), spec_for(Channel.SMTP_SEND), START)

        self.assertEqual(rate.rate, 100.0)
        self.assertFalse(rate.manual_capped)
        self.assertEqual(rate.tolerance, 0)

    def test_a_lowered_settings_ceiling_caps_a_stored_manual_rate(self):
        policy = policy_for(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=24)
        spec = spec_for(Channel.GRAPH_SEND, provider_limit=20)

        rate = effective_rate(policy, state_for(Channel.GRAPH_SEND), spec, START)

        self.assertEqual(rate.rate, 20.0)

    def test_smart_rate_would_use_is_reported_while_manual(self):
        policy = policy_for(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=10)
        state = state_for(Channel.GRAPH_SEND)

        self.assertAlmostEqual(smart_rate(policy, state, spec_for(Channel.GRAPH_SEND), START), 24.0)


class BoundTests(SimpleTestCase):
    def test_the_bound_is_the_smallest_of_operator_documented_and_reported(self):
        spec = spec_for(Channel.GRAPH_SEND)
        cases = (
            ({}, {}, 30, BoundSource.DOCUMENTED),
            ({"provider_limit": 25}, {}, 25, BoundSource.OPERATOR),
            ({"provider_limit": 25}, {"discovered_rate": 12.0}, 12, BoundSource.REPORTED),
            ({}, {"discovered_rate": 50.0}, 30, BoundSource.DOCUMENTED),
        )
        for policy_values, state_values, value, source in cases:
            with self.subTest(policy=policy_values, state=state_values):
                bound = rate_bound(
                    policy_for(Channel.GRAPH_SEND, **policy_values), state_for(Channel.GRAPH_SEND, **state_values), spec
                )
                self.assertEqual((bound.value, bound.source), (value, source))

    def test_a_reported_limit_wins_a_tie(self):
        bound = rate_bound(
            policy_for(Channel.SES_SEND, provider_limit=14),
            state_for(Channel.SES_SEND, discovered_rate=14.0),
            spec_for(Channel.SES_SEND),
        )

        self.assertEqual(bound.source, BoundSource.REPORTED)

    def test_last_known_report_beats_the_fallback_after_a_failed_refresh(self):
        state = state_for(
            Channel.SES_SEND,
            discovered_rate=14.0,
            discovered_at=START - timedelta(hours=26),
            discovery_error="AccessDenied: ses:GetAccount",
        )

        bound = rate_bound(policy_for(Channel.SES_SEND), state, spec_for(Channel.SES_SEND))

        self.assertEqual((bound.value, bound.source), (14.0, BoundSource.REPORTED))

    def test_the_fallback_is_used_only_when_nothing_is_known(self):
        bound = rate_bound(policy_for(Channel.SES_SEND), state_for(Channel.SES_SEND), spec_for(Channel.SES_SEND))

        self.assertEqual((bound.value, bound.source), (1.0, BoundSource.FALLBACK))
        self.assertFalse(bound.known)

    def test_a_carried_over_limit_stands_in_only_until_the_provider_reports_one(self):
        policy = policy_for(Channel.SES_SEND, provider_limit=10, provider_limit_carried_over=True)
        spec = spec_for(Channel.SES_SEND)
        cases = ((None, 10, BoundSource.CARRIED_OVER), (14.0, 14, BoundSource.REPORTED), (5.0, 5, BoundSource.REPORTED))
        for reported, value, source in cases:
            with self.subTest(reported=reported):
                bound = rate_bound(policy, state_for(Channel.SES_SEND, discovered_rate=reported), spec)
                self.assertEqual((bound.value, bound.source), (value, source))
                self.assertTrue(bound.known)

    def test_an_operator_limit_still_caps_a_higher_report(self):
        bound = rate_bound(
            policy_for(Channel.SES_SEND, provider_limit=10),
            state_for(Channel.SES_SEND, discovered_rate=14.0),
            spec_for(Channel.SES_SEND),
        )

        self.assertEqual((bound.value, bound.source), (10, BoundSource.OPERATOR))

    def test_smart_ses_runs_at_the_reported_limit_once_it_replaces_the_carried_over_one(self):
        policy = policy_for(Channel.SES_SEND, provider_limit=10, manual_rate=10, provider_limit_carried_over=True)
        spec = spec_for(Channel.SES_SEND)
        smart = {"mode": SMART, "factor_base": 1.0, "factor_changed_at": START}

        before = effective_rate(policy, state_for(Channel.SES_SEND, **smart), spec, START)
        after = effective_rate(policy, state_for(Channel.SES_SEND, discovered_rate=14.0, **smart), spec, START)

        self.assertAlmostEqual(before.rate, 9.0)
        self.assertAlmostEqual(after.rate, 14 * 0.9)

    def test_a_zero_or_missing_report_is_ignored(self):
        state = state_for(Channel.SES_SEND, discovered_rate=0.0)

        bound = rate_bound(policy_for(Channel.SES_SEND, provider_limit=7), state, spec_for(Channel.SES_SEND))

        self.assertEqual(bound.source, BoundSource.OPERATOR)
