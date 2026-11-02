"""The Smart rate controller in isolation: lazy recovery, one cut per episode, the floor, the freeze, and the
backoff with jitter."""

import random
from datetime import timedelta

from django.test import SimpleTestCase

from apps.core.models import DeliveryRateState
from apps.core.services.delivery_rates.rules import controller, signals

from .helpers import START, Channel, spec_for, state_for

SMART = DeliveryRateState.Mode.SMART


def smart_state(factor=1.0, changed=START, **values):
    return state_for(Channel.GRAPH_SEND, mode=SMART, factor_base=factor, factor_changed_at=changed, **values)


class RecoveryTests(SimpleTestCase):
    def test_recovery_adds_one_step_per_whole_interval(self):
        spec = spec_for(Channel.GRAPH_SEND)  # +0.10 per 600 s
        state = smart_state(factor=0.5)
        cases = ((0, 0.5), (599, 0.5), (600, 0.6), (1_799, 0.7), (3_000, 1.0), (86_400, 1.0))
        for seconds, factor in cases:
            with self.subTest(seconds=seconds):
                now = START + timedelta(seconds=seconds)
                self.assertAlmostEqual(controller.current_factor(state, spec, now), factor)

    def test_full_speed_time(self):
        spec = spec_for(Channel.GRAPH_SEND)

        self.assertEqual(controller.full_speed_at(smart_state(factor=0.4), spec, START), START + timedelta(minutes=60))
        self.assertIsNone(controller.full_speed_at(smart_state(factor=1.0), spec, START))


class CutTests(SimpleTestCase):
    def test_a_cut_halves_the_current_factor(self):
        spec = spec_for(Channel.GRAPH_SEND)
        state = smart_state(factor=0.5)
        now = START + timedelta(seconds=1_200)  # recovered to 0.7

        self.assertTrue(controller.cut(state, spec, now, admitted_at=now - timedelta(seconds=1)))
        self.assertAlmostEqual(state.factor_base, 0.35)
        self.assertEqual((state.factor_changed_at, state.last_cut_at), (now, now))

    def test_requests_admitted_before_the_last_cut_cannot_cut_again(self):
        spec = spec_for(Channel.GRAPH_SEND)
        state = smart_state()
        admitted = START
        first, second, third = (START + timedelta(seconds=n) for n in (1, 2, 3))

        self.assertTrue(controller.cut(state, spec, first, admitted))
        self.assertFalse(controller.cut(state, spec, second, admitted))
        self.assertFalse(controller.cut(state, spec, third, admitted))
        self.assertEqual(state.factor_base, 0.5)
        # A request admitted after the cut starts a new episode.
        self.assertTrue(controller.cut(state, spec, START + timedelta(seconds=5), START + timedelta(seconds=4)))
        self.assertEqual(state.factor_base, 0.25)

    def test_the_factor_never_falls_below_the_floor_nor_rises_above_one(self):
        spec = spec_for(Channel.GRAPH_SEND)
        rng = random.Random(7)
        state, now = smart_state(), START
        for _ in range(500):
            now += timedelta(seconds=rng.choice([0, 1, 60, 600, 3_600]))
            action = rng.random()
            if action < 0.4:
                controller.cut(state, spec, now, admitted_at=now)
            elif action < 0.5:
                controller.freeze(state, spec, now)
            factor = controller.current_factor(state, spec, now)
            self.assertGreaterEqual(factor, spec.floor)
            self.assertLessEqual(factor, 1.0)

    def test_manual_mode_is_never_cut_nor_frozen(self):
        spec = spec_for(Channel.GRAPH_SEND)
        state = state_for(Channel.GRAPH_SEND, mode="manual", factor_base=1.0)

        self.assertFalse(controller.cut(state, spec, START, START - timedelta(seconds=1)))
        controller.freeze(state, spec, START)
        self.assertEqual((state.factor_base, state.factor_changed_at), (1.0, None))

    def test_freeze_keeps_the_factor_and_restarts_the_recovery_clock(self):
        spec = spec_for(Channel.GRAPH_SEND)
        state = smart_state(factor=0.5)
        now = START + timedelta(seconds=900)  # 0.6, half way to the next step

        controller.freeze(state, spec, now)

        self.assertAlmostEqual(state.factor_base, 0.6)
        self.assertAlmostEqual(controller.current_factor(state, spec, now + timedelta(seconds=599)), 0.6)


class BackoffTests(SimpleTestCase):
    def test_backoff_doubles_up_to_the_maximum_within_the_jitter(self):
        spec = spec_for(Channel.GRAPH_SEND)  # 5 s → 120 s, ± 20 %
        rng = random.Random(1)
        for consecutive, base in ((1, 5), (2, 10), (3, 20), (5, 80), (6, 120), (60, 120), (10_000, 120)):
            with self.subTest(consecutive=consecutive):
                seconds = controller.backoff_seconds(consecutive, spec, rng)
                self.assertGreaterEqual(seconds, base * 0.8)
                self.assertLessEqual(seconds, base * 1.2)

    def test_retry_after_wins_then_the_settings_pause_then_the_backoff(self):
        spec = spec_for(Channel.GRAPH_SEND, backoff_jitter=0)

        self.assertEqual(controller.cooldown_seconds(signals.throttle(retry_after=7), 3, spec), 7)
        self.assertEqual(controller.cooldown_seconds(signals.pause("sign_in", seconds=300), 3, spec), 300)
        self.assertEqual(controller.cooldown_seconds(signals.throttle(), 3, spec), 20)
