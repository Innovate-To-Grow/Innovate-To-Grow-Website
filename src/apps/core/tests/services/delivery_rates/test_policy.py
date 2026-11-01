"""The precedence rule (``effective_rate``): Smart rate on ignores the manual rate, Smart rate off returns it
exactly (capped only at a provider limit), last-known reports beat the fallback, and the burst never lets the steady
rate plus the burst exceed the bound."""

from datetime import timedelta

from django.test import SimpleTestCase

from apps.core.models import DeliveryRateState
from apps.core.services.delivery_rates.rules.controller import sync_mode
from apps.core.services.delivery_rates.rules.policy import BoundSource, effective_rate, rate_bound, smart_rate

from .helpers import START, Channel, policy_for, spec_for, state_for

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


class ToleranceTests(SimpleTestCase):
    def test_burst_is_clipped_so_rate_plus_burst_stays_within_the_bound(self):
        state = state_for(Channel.GRAPH_SEND, mode=SMART, factor_base=1.0, factor_changed_at=START)
        cases = (
            # Smart 24/min of 30: room for the whole burst of 3 (two beyond the steady rate).
            (policy_for(Channel.GRAPH_SEND), 2),
            # Manual 30/min of 30: no room left for any burst.
            (policy_for(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=30), 0),
            # Manual 29/min of 30: room for one.
            (policy_for(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=29), 1),
        )
        for policy, tolerance in cases:
            with self.subTest(manual=policy.manual_rate, smart=policy.smart_enabled):
                self.assertEqual(
                    effective_rate(policy, state, spec_for(Channel.GRAPH_SEND), START).tolerance, tolerance
                )

    def test_a_fractional_bound_counts_only_whole_requests(self):
        policy = policy_for(Channel.SES_SEND, smart_enabled=False, manual_rate=13.2, provider_limit=14.5)

        rate = effective_rate(policy, state_for(Channel.SES_SEND), spec_for(Channel.SES_SEND), START)

        self.assertAlmostEqual(rate.tolerance, 0.8)


class WholeRequestCeilingTests(SimpleTestCase):
    """A window holds whole requests: under a fractional bound B ≥ 1 the pace never exceeds ⌊B⌋."""

    def test_a_manual_rate_at_a_fractional_limit_paces_at_its_whole_part(self):
        for manual in (14.5, 14.2):
            with self.subTest(manual=manual):
                policy = policy_for(Channel.SES_SEND, smart_enabled=False, manual_rate=manual, provider_limit=14.5)
                rate = effective_rate(policy, state_for(Channel.SES_SEND), spec_for(Channel.SES_SEND), START)
                self.assertEqual((rate.rate, rate.tolerance), (14.0, 0.0))
                self.assertTrue(rate.manual_capped)

    def test_smart_rate_at_full_speed_paces_at_the_whole_part(self):
        spec = spec_for(Channel.SES_SEND, provider_limit=14.5, headroom=1.0)
        state = state_for(Channel.SES_SEND, mode=SMART, factor_base=1.0, factor_changed_at=START)

        rate = effective_rate(policy_for(Channel.SES_SEND), state, spec, START)

        self.assertEqual(rate.rate, 14.0)
        self.assertEqual(smart_rate(policy_for(Channel.SES_SEND, smart_enabled=False), state, spec, START), 14.0)

    def test_a_bound_below_one_per_window_is_kept_as_is(self):
        policy = policy_for(Channel.SES_SEND, smart_enabled=False, manual_rate=0.5, provider_limit=0.5)

        rate = effective_rate(policy, state_for(Channel.SES_SEND), spec_for(Channel.SES_SEND), START)

        self.assertEqual(rate.rate, 0.5)
        self.assertFalse(rate.manual_capped)

    def test_the_fallback_still_never_caps_a_manual_rate(self):
        policy = policy_for(Channel.SMTP_SEND, smart_enabled=False, manual_rate=60.5)

        rate = effective_rate(policy, state_for(Channel.SMTP_SEND), spec_for(Channel.SMTP_SEND), START)

        self.assertEqual(rate.rate, 60.5)

    def test_sms_parts_pace_at_the_whole_part_of_a_fractional_mps(self):
        state = state_for(Channel.SMS_SEND, discovered_parts_rate=2.5)

        manual = effective_rate(
            policy_for(Channel.SMS_SEND, smart_enabled=False), state, spec_for(Channel.SMS_SEND), START
        )

        self.assertEqual(manual.parts_rate, 2.0)


class SmsPrecedenceTests(SimpleTestCase):
    def test_smart_rate_scales_both_the_message_and_the_parts_rate(self):
        state = state_for(
            Channel.SMS_SEND, mode=SMART, factor_base=0.5, factor_changed_at=START, discovered_parts_rate=3.0
        )

        rate = effective_rate(policy_for(Channel.SMS_SEND), state, spec_for(Channel.SMS_SEND), START)

        self.assertAlmostEqual(rate.rate, 0.5)
        self.assertAlmostEqual(rate.parts_rate, 1.5)
        self.assertEqual(rate.parts.source, BoundSource.REPORTED)

    def test_manual_rate_scales_only_messages_and_parts_stay_the_provider_cap(self):
        policy = policy_for(Channel.SMS_SEND, smart_enabled=False, manual_rate="0.5")
        state = state_for(Channel.SMS_SEND, discovered_parts_rate=3.0)

        rate = effective_rate(policy, state, spec_for(Channel.SMS_SEND), START)

        self.assertEqual((rate.rate, rate.parts_rate), (0.5, 3.0))

    def test_parts_fall_back_to_one_per_second_until_aws_reports_the_number(self):
        rate = effective_rate(
            policy_for(Channel.SMS_SEND), state_for(Channel.SMS_SEND), spec_for(Channel.SMS_SEND), START
        )

        self.assertEqual((rate.parts.value, rate.parts.source), (1.0, BoundSource.FALLBACK))

    def test_non_sms_channels_have_no_parts(self):
        rate = effective_rate(
            policy_for(Channel.SES_SEND), state_for(Channel.SES_SEND), spec_for(Channel.SES_SEND), START
        )

        self.assertIsNone(rate.parts)


class ModeSwitchTests(SimpleTestCase):
    def test_switching_smart_rate_on_resets_the_factor_and_keeps_the_cooldown(self):
        spec = spec_for(Channel.GRAPH_SEND)
        cooldown = START + timedelta(minutes=5)
        state = state_for(Channel.GRAPH_SEND, mode="manual", factor_base=0.25, cooldown_until=cooldown)

        changed = sync_mode(state, True, spec, START, limit_known=True)

        self.assertTrue(changed)
        self.assertEqual((state.mode, state.factor_base, state.factor_changed_at), (SMART, 1.0, START))
        self.assertEqual(state.cooldown_until, cooldown)

    def test_switching_on_without_a_known_limit_starts_lower(self):
        state = state_for(Channel.SMTP_SEND, mode="manual")

        sync_mode(state, True, spec_for(Channel.SMTP_SEND), START, limit_known=False)

        self.assertEqual(state.factor_base, 0.5)

    def test_switching_smart_rate_off_changes_nothing_but_the_mode(self):
        state = state_for(Channel.GRAPH_SEND, mode=SMART, factor_base=0.5, factor_changed_at=START)

        self.assertTrue(sync_mode(state, False, spec_for(Channel.GRAPH_SEND), START, limit_known=True))
        self.assertEqual((state.mode, state.factor_base), ("manual", 0.5))
        self.assertFalse(sync_mode(state, False, spec_for(Channel.GRAPH_SEND), START, limit_known=True))
