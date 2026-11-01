"""Shared test helpers: a fake clock the limiter sleeps on, in-memory policies and states for the pure rules, and
settings overrides."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings

from apps.core.models import DeliveryRatePolicy, DeliveryRateState
from apps.core.services.delivery_rates.rules.defaults import rate_spec

Channel = DeliveryRatePolicy.Channel
START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class FakeClock:
    """``now()`` for the limiter, and a ``sleep()`` that moves it forward instead of waiting."""

    def __init__(self, start=START):
        self.current = start
        self.slept = []

    def now(self):
        return self.current

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.current += timedelta(seconds=seconds)

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)

    def install(self, test):
        """Patch the limiter's clock and sleep for the rest of ``test``."""
        for name, target in (("clock", self.now), ("sleep", self.sleep)):
            patcher = patch(f"apps.core.services.delivery_rates.runtime.context.{name}", target)
            patcher.start()
            test.addCleanup(patcher.stop)
        return self


def spec_for(channel, **overrides):
    return replace(rate_spec(channel), **overrides)


def policy_for(channel, **values):
    """An in-memory policy row with the channel's seeds (pure tests never save it)."""
    seeds = DeliveryRatePolicy.seed_values(channel)
    fields = {"provider_limit": None, "parts_limit": None, **seeds, **values}
    for name in ("manual_rate", "provider_limit", "parts_limit"):
        if fields[name] is not None:
            fields[name] = Decimal(str(fields[name]))
    return SimpleNamespace(channel=channel, **fields)


def state_for(channel, **values):
    """An unsaved state row (all defaults), for the pure rules."""
    return DeliveryRateState(channel=channel, identity="test", cooldown_group="test", **values)


def rates_with(**sections):
    """DELIVERY_RATES with ``channels={name: {key: value}}`` or ``controller={...}``-style updates merged in."""
    rates = copy.deepcopy(settings.DELIVERY_RATES)
    for section, values in sections.items():
        if section == "channels":
            for channel, channel_values in values.items():
                rates["channels"][channel].update(channel_values)
        else:
            rates[section].update(values)
    return rates


def set_policy(channel, **values):
    policy = DeliveryRatePolicy.for_channel(channel)
    for name, value in values.items():
        setattr(policy, name, value)
    policy.save()
    return policy


def spy_on_email_admissions(test):
    """Record every email admission (the real limiter still runs); returns the mock whose calls show channel,
    identity and lane: ``spy.call_args.kwargs["lane"]``."""
    from apps.core.services.email import delivery

    patcher = patch.object(delivery, "admit", wraps=delivery.admit)
    spy = patcher.start()
    test.addCleanup(patcher.stop)
    return spy
