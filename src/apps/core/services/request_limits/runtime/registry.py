"""The in-process view of every scope: its ``REQUEST_RATE_LIMITS`` baseline, its policy row and its Smart factor.

Read on every request, loaded from the database at most every ``controller.state_refresh_seconds`` (so another
process's Smart cut or an admin change arrives within that time) and at once after a save in this process
(``receivers``) or a settings change. A missing row is created from its seed (a deleted row heals itself); while a
scope's Smart limit is off its factor is held at 1, so switching Smart back on starts at full speed. When the
database cannot be read the last view is kept, or the seeds are used before the first load: the limiter never
fails a request for want of its policy.
"""

import logging
import threading

from django.db import DatabaseError

from apps.core.models import RequestRateLimitPolicy, RequestRateLimitState

from ..rules.limits import ScopeConfig
from .context import as_seconds, section

logger = logging.getLogger(__name__)


class _Registry:
    def __init__(self):
        self.lock = threading.Lock()
        self.loaded_at: float | None = None
        self.configs: dict[str, ScopeConfig] = {}


REGISTRY = _Registry()


def invalidate(**_kwargs) -> None:
    REGISTRY.loaded_at = None


def build(scope: str, spec: dict, policy=None, state=None) -> ScopeConfig:
    """``scope``'s config from its settings ``spec`` and, when given, its policy row and Smart state."""
    values = (
        policy
        if policy is not None
        else RequestRateLimitPolicy(scope=scope, **RequestRateLimitPolicy.seed_values(scope))
    )
    return ScopeConfig(
        scope=scope,
        label=values.label,
        tier=values.tier,
        identity=values.identity,
        baseline=spec["requests"],
        manual=values.manual_requests,
        period=values.period_seconds,
        smart=values.smart_enabled,
        floor=float(values.smart_floor),
        fixed=values.fixed,
        enabled=values.enabled,
        ceiling=values.identity_ceiling,
        global_cap=values.global_cap,
        factor=state.factor if state is not None else 1.0,
        factor_changed_at=as_seconds(state.factor_changed_at) if state is not None else None,
        last_cut_at=as_seconds(state.last_cut_at) if state is not None else None,
    )


def _rows(specs):
    policies = {row.scope: row for row in RequestRateLimitPolicy.objects.filter(scope__in=list(specs))}
    for scope in specs:
        if scope not in policies:
            policies[scope] = RequestRateLimitPolicy.for_scope(scope)
    states = {row.scope: row for row in RequestRateLimitState.objects.filter(scope__in=list(specs))}
    for scope in specs:
        if scope not in states:
            states[scope], _created = RequestRateLimitState.objects.get_or_create(scope=scope)
        state = states[scope]
        if not policies[scope].smart_enabled and state.factor != 1.0:
            RequestRateLimitState.objects.filter(pk=state.pk).update(
                factor=1.0, factor_changed_at=None, last_cut_at=None
            )
            state.factor, state.factor_changed_at, state.last_cut_at = 1.0, None, None
    return policies, states


def _load(now: float) -> None:
    specs = section("scopes")
    try:
        policies, states = _rows(specs)
        REGISTRY.configs = {scope: build(scope, spec, policies[scope], states[scope]) for scope, spec in specs.items()}
    except DatabaseError:
        logger.warning("request_limits.policy_unavailable", exc_info=True)
        if not REGISTRY.configs:
            REGISTRY.configs = {scope: build(scope, spec) for scope, spec in specs.items()}
    REGISTRY.loaded_at = now


def configs(now: float) -> dict[str, ScopeConfig]:
    """Every scope's config, refreshed when due."""
    due = REGISTRY.loaded_at is None or now - REGISTRY.loaded_at >= section("controller")["state_refresh_seconds"]
    # The first load (or one after an invalidation) waits for the lock; later refreshes are done by one thread
    # while the others keep reading the current view.
    if due and REGISTRY.lock.acquire(blocking=REGISTRY.loaded_at is None):
        try:
            if REGISTRY.loaded_at is None or now - REGISTRY.loaded_at >= section("controller")["state_refresh_seconds"]:
                _load(now)
        finally:
            REGISTRY.lock.release()
    return REGISTRY.configs


def replace(config: ScopeConfig) -> None:
    """Put a config this process just changed into the view (the database has it already)."""
    REGISTRY.configs = {**REGISTRY.configs, config.scope: config}
