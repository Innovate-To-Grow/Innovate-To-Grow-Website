from datetime import timedelta

from django.test import SimpleTestCase

from apps.core.services.delivery_rates.rules.controller import sync_mode
from apps.core.services.delivery_rates.rules.policy import BoundSource, effective_rate, smart_rate
from apps.core.tests.services.delivery_rates.policy.test_policy import SMART

from ..helpers import START, Channel, policy_for, spec_for, state_for


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
