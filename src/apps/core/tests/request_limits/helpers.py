"""Shared helpers for the request-limit tests: a fake clock, a clean in-process state per test, settings overrides
with small test scopes, and a URLconf of views in each tier."""

import copy
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings

from apps.core.services.request_limits import scopes as scope_module
from apps.core.services.request_limits.identity import _RESOLVERS
from apps.core.services.request_limits.runtime import heartbeat, registry, signals, smart

START = 1_800_000_000.0  # a fixed epoch second (2027-01-15), aligned to a whole minute


class FakeClock:
    def __init__(self, start=START):
        self.current = start

    def __call__(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


def reset_runtime():
    """Forget every in-process request-limit state (policy view, windows, slots, heartbeat, registrations)."""
    registry.invalidate()
    registry.REGISTRY.configs = {}
    signals.WINDOW.reset()
    signals.INFLIGHT.count = 0
    heartbeat.PROCESS.reset()
    smart.LAST.clear()
    scope_module._REGISTERED.clear()
    scope_module._EXEMPTIONS.clear()
    _RESOLVERS.clear()


def isolate(test, start=START) -> FakeClock:
    """A fresh runtime and cache and a fake clock for the rest of ``test``."""
    cache.clear()
    reset_runtime()
    test.addCleanup(reset_runtime)
    clock = FakeClock(start)
    patcher = patch("apps.core.services.request_limits.runtime.context.clock", clock)
    patcher.start()
    test.addCleanup(patcher.stop)
    return clock


def make_scope(tier, requests=100, *, identity="ip", global_cap=None, fixed=False, floor=None, ceiling=None):
    return {
        "label": f"Test {tier}",
        "description": "",
        "tier": tier,
        "identity": identity,
        "requests": requests,
        "period_seconds": 60,
        "smart_enabled": True,
        "smart_floor": floor,
        "fixed": fixed,
        "enabled": True,
        "identity_ceiling": ceiling,
        "global_cap": global_cap,
    }


TEST_SCOPES = {
    "t-p0": make_scope("p0", 5, identity="member", global_cap=1_000),
    "t-p1": make_scope("p1", 1_000, global_cap=10_000),
    "t-p2": make_scope("p2", 1_000, global_cap=10_000),
    "t-p3": make_scope("p3", 1_000, global_cap=10_000),
    "t-fixed": make_scope("p2", 1_000, global_cap=10_000, fixed=True),
}


def limits_with(scopes=None, **sections):
    """REQUEST_RATE_LIMITS with the test scopes (or ``scopes``) added and sections updated key by key."""
    config = copy.deepcopy(settings.REQUEST_RATE_LIMITS)
    config["scopes"].update(TEST_SCOPES if scopes is None else scopes)
    for section, values in sections.items():
        config[section] = {**config[section], **values}
    return config


def limiter_on(scopes=None, **sections):
    """override_settings turning the limiter on with the test scopes (or ``scopes``) and the test URLconf."""
    return override_settings(
        REQUEST_RATE_LIMITS_ENABLED=True,
        REQUEST_RATE_LIMITS=limits_with(scopes, **sections),
        ROOT_URLCONF="apps.core.tests.request_limits.urls",
    )


def view_limits_with(**rates):
    """REQUEST_RATE_LIMITS with per-view limit seeds changed: ``view_limits_with(**{"view-ai-search": (2, 60)})``
    (requests, period seconds), or ``None`` to switch one off."""
    config = copy.deepcopy(settings.REQUEST_RATE_LIMITS)
    for scope, rate in rates.items():
        spec = {**config["scopes"][scope]}
        if rate is None:
            spec["enabled"] = False
        else:
            spec["requests"], spec["period_seconds"] = rate
        config["scopes"][scope] = spec
    return config


def view_limit(**rates):
    """override_settings changing per-view limit seeds (the rates the throttles use while the limiter is off, as in
    the test settings), e.g. ``@view_limit(**{"view-past-project-share": (1, 60)})``."""
    return override_settings(REQUEST_RATE_LIMITS=view_limits_with(**rates))
