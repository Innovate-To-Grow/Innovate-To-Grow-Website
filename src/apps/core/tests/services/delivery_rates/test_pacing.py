"""GCRA pacing properties: in any window W of the channel's unit, admissions stay within rate·W + burst and within
the provider bound; campaigns get at most their share; a cooldown ends without a burst; SMS parts set the spacing."""

import math
import random
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.models import DeliveryRateState
from apps.core.services.delivery_rates.rules.pacing import increment_seconds, next_slot, tolerance_seconds
from apps.core.services.delivery_rates.rules.policy import effective_rate

from .helpers import START, Channel, policy_for, spec_for, state_for

SMART = DeliveryRateState.Mode.SMART


def run(rate, *, count, gaps=None, bulk_share=None, parts=None, cooldown_until=None, start=START):
    """Send ``count`` requests as soon as each is allowed (plus an optional idle gap before some); return the send
    times."""
    tat = tat_bulk = None
    now, sent = start, []
    increment, tolerance = increment_seconds(rate, 1, parts), tolerance_seconds(rate)
    for index in range(count):
        if gaps:
            now += timedelta(seconds=gaps(index))
        slot = next_slot(
            now=now,
            tat=tat,
            tat_bulk=tat_bulk,
            cooldown_until=cooldown_until,
            increment=increment,
            tolerance=tolerance,
            bulk_share=bulk_share,
        )
        tat, tat_bulk = slot.tat, slot.tat_bulk
        now = slot.at
        sent.append(slot.at)
    return sent


def busiest_window(times, seconds):
    """Most sends in any half-open window [t, t + seconds)."""
    best, low = 0, 0
    window = timedelta(seconds=seconds)
    for high, moment in enumerate(times):
        while moment - times[low] >= window:
            low += 1
        best = max(best, high - low + 1)
    return best


def smart_state(channel, factor=1.0, **values):
    return state_for(channel, mode=SMART, factor_base=factor, factor_changed_at=START, **values)


class WindowPropertyTests(SimpleTestCase):
    def test_graph_manual_30_sends_at_most_30_in_any_minute(self):
        policy = policy_for(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=30)
        rate = effective_rate(policy, state_for(Channel.GRAPH_SEND), spec_for(Channel.GRAPH_SEND), START)

        self.assertEqual(busiest_window(run(rate, count=200), 60), 30)

    def test_graph_smart_24_sends_at_most_26_in_any_minute(self):
        rate = effective_rate(
            policy_for(Channel.GRAPH_SEND), smart_state(Channel.GRAPH_SEND), spec_for(Channel.GRAPH_SEND), START
        )

        self.assertAlmostEqual(rate.rate, 24)
        self.assertEqual(busiest_window(run(rate, count=200), 60), 26)

    def test_ses_smart_stays_within_the_reported_14_per_second(self):
        state = smart_state(Channel.SES_SEND, discovered_rate=14.0)
        rate = effective_rate(policy_for(Channel.SES_SEND), state, spec_for(Channel.SES_SEND), START)

        self.assertLessEqual(busiest_window(run(rate, count=500), 1), 14)

    def test_random_policies_never_exceed_rate_plus_burst_nor_the_bound(self):
        rng = random.Random(643)
        for case in range(150):
            channel = rng.choice([Channel.GRAPH_SEND, Channel.SES_SEND, Channel.GMAIL_API_SEND, Channel.SMTP_SEND])
            bound = rng.choice([1, 2, 7, 14, 30, 60, 100, 14.5])
            burst = rng.randint(1, 5)
            spec = spec_for(channel, provider_limit=bound, burst=burst, headroom=rng.choice([1.0, 0.9, 0.8, 0.5]))
            smart = rng.random() < 0.5
            manual = Decimal(str(round(rng.uniform(0.1, bound), 3)))
            policy = policy_for(channel, smart_enabled=smart, manual_rate=manual, provider_limit=None)
            state = smart_state(channel, factor=rng.choice([1.0, 0.7, 0.25]))
            rate = effective_rate(policy, state, spec, START)
            window = spec.window
            idle = lambda index, rng=rng, window=window: rng.choice([0, 0, 0, window * rng.random() * 2])  # noqa: E731
            with self.subTest(case=case, channel=channel, bound=bound, burst=burst, smart=smart, manual=manual):
                busiest = busiest_window(run(rate, count=300, gaps=idle), window)
                self.assertLessEqual(busiest, math.floor(rate.rate + burst + 1e-9))
                self.assertLessEqual(busiest, max(math.floor(bound), math.ceil(rate.rate - 1e-9)))


class LanesAndCooldownTests(SimpleTestCase):
    def test_campaigns_get_at_most_the_bulk_share_of_the_rate(self):
        policy = policy_for(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=30)
        rate = effective_rate(policy, state_for(Channel.GRAPH_SEND), spec_for(Channel.GRAPH_SEND), START)

        sent = run(rate, count=200, bulk_share=0.8)

        self.assertEqual(busiest_window(sent, 60), 24)

    def test_requests_waiting_out_a_cooldown_leave_one_interval_apart(self):
        rate = effective_rate(
            policy_for(Channel.GRAPH_SEND), smart_state(Channel.GRAPH_SEND), spec_for(Channel.GRAPH_SEND), START
        )
        cooldown = START + timedelta(seconds=10)

        sent = run(rate, count=5, cooldown_until=cooldown)

        self.assertEqual(sent[0], cooldown)
        gaps = [(later - earlier).total_seconds() for earlier, later in zip(sent, sent[1:], strict=False)]
        self.assertTrue(all(math.isclose(gap, 2.5, abs_tol=1e-6) for gap in gaps), gaps)

    def test_without_a_cooldown_the_burst_goes_out_back_to_back(self):
        rate = effective_rate(
            policy_for(Channel.GRAPH_SEND), smart_state(Channel.GRAPH_SEND), spec_for(Channel.GRAPH_SEND), START
        )

        self.assertEqual(run(rate, count=4)[:3], [START] * 3)


class SmsPartsSpacingTests(SimpleTestCase):
    """Toll-free number: 3 message parts per second (reported), 1 SendTextMessage request per second."""

    def rate(self, factor):
        state = smart_state(Channel.SMS_SEND, factor=factor, discovered_parts_rate=3.0)
        return effective_rate(policy_for(Channel.SMS_SEND), state, spec_for(Channel.SMS_SEND), START)

    def test_one_part_messages_are_spaced_by_the_request_rate(self):
        self.assertAlmostEqual(increment_seconds(self.rate(1.0), 1, 1), 1.0)

    def test_four_parts_are_spaced_by_the_parts_rate(self):
        self.assertAlmostEqual(increment_seconds(self.rate(1.0), 1, 4), 4 / 3)

    def test_a_smart_rate_cut_also_slows_one_part_messages(self):
        self.assertAlmostEqual(increment_seconds(self.rate(0.5), 1, 1), 2.0)

    def test_sends_follow_the_part_spacing(self):
        sent = run(self.rate(1.0), count=6, parts=4)

        gaps = [(later - earlier).total_seconds() for earlier, later in zip(sent, sent[1:], strict=False)]
        self.assertTrue(all(math.isclose(gap, 4 / 3, abs_tol=1e-5) for gap in gaps), gaps)
