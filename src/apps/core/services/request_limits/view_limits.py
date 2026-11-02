"""The finer, per-view limits (``config/settings/base/integrations/request_limits/view_scopes.py``), read live.

Each per-view limit is a request-limit scope with a ``parent`` route scope. ``view_rate(scope)`` is its rate now:

- request limiter on: the scope's policy row as this process sees it (``runtime.registry``: re-read every
  ``controller.state_refresh_seconds``, at once after a save in this process), so an admin edit applies without a
  restart. Smart limit on (the default) takes priority over the manual limit: the seed × the parent's Smart factor,
  clamped to the scope's floor, and never tightened for a P0 or fixed scope; Smart off: the manual limit (capped by
  the per-caller ceiling); disabled: no limit;
- request limiter off (``REQUEST_RATE_LIMITS_ENABLED`` false, as in the test settings): the seed from
  ``REQUEST_RATE_LIMITS``, without reading the database: the behaviour before this feature.

The views keep their own keys, caches and windows (DRF's sliding history); the limits are not divided by the live
process count. ``PolicyRateThrottle`` / ``MemberRateThrottle`` are the DRF bases; ``failure_lockout`` and
``record_failure`` count failures (a shared password) in the request-limit counter store (with per-process counters,
each process allows its share of the live processes, like the route limits).
"""

import math
from dataclasses import dataclass, replace

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

from .limiter import live_processes
from .rules.limits import effective_limits
from .runtime import context, registry, store
from .runtime.context import section


@dataclass(frozen=True)
class ViewRate:
    requests: int
    period: int


def _seed(spec) -> ViewRate | None:
    return ViewRate(spec["requests"], spec["period_seconds"]) if spec["enabled"] else None


def view_rate(scope: str) -> ViewRate | None:
    """The per-view limit ``scope``'s rate now, or None when it does not limit."""
    spec = section("scopes")[scope]
    if not settings.REQUEST_RATE_LIMITS_ENABLED:
        return _seed(spec)
    configs = registry.configs(context.clock())
    config = configs.get(scope)
    if config is None:
        return _seed(spec)
    if not config.enabled:
        return None
    parent = configs.get(spec["parent"])
    factor = parent.factor if parent is not None and parent.smart else 1.0
    limits = effective_limits(replace(config, factor=factor))
    return ViewRate(limits.per_identity, limits.period)


class PolicyRateThrottle(SimpleRateThrottle):
    """A DRF throttle whose rate is the per-view limit ``policy_scope``, read on every request (DRF builds a new
    throttle per request). ``scope`` stays the cache-key prefix, so the keys are what they always were."""

    policy_scope = ""

    def get_rate(self):
        return view_rate(self.policy_scope)

    def parse_rate(self, rate):
        if rate is None:
            return None, None
        return rate.requests, rate.period


class MemberRateThrottle(PolicyRateThrottle):
    """Per signed-in member (the key DRF's ``UserRateThrottle`` uses for one). An anonymous request is not limited
    here, never keyed on the client IP: these throttles sit on views that require a member, and sign-in and code
    flows must not share a campus-wide bucket."""

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": user.pk}


def _window(scope: str, bucket: str, now: float):
    rate = view_rate(scope)
    if rate is None:
        return None, None
    return rate, store.window_key(f"fail|{scope}|{bucket}", rate.period, now)


def failure_lockout(scope: str, bucket: str = "*") -> int | None:
    """Seconds until ``bucket`` may try again when it has used up the per-view limit ``scope``'s failures in the
    current window (fixed windows in the counter store), else None."""
    now = context.clock()
    rate, name = _window(scope, bucket, now)
    if rate is None:
        return None
    allowed = rate.requests
    if settings.REQUEST_RATE_LIMITS_ENABLED:
        # Per-process counters (no shared store): each process allows its share, so the site-wide total holds.
        allowed = max(1, math.ceil(allowed / live_processes(now)))
    failures = store.get(name)
    if isinstance(failures, int) and failures >= allowed:
        return store.window_reset(rate.period, now)
    return None


def record_failure(scope: str, bucket: str = "*") -> None:
    """Count one failure of ``bucket`` against the per-view limit ``scope``."""
    now = context.clock()
    rate, _name = _window(scope, bucket, now)
    if rate is not None:
        store.hit(f"fail|{scope}|{bucket}", rate.period, now)
