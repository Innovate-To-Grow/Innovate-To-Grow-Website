"""What Site Settings → Request Limits shows: every scope's limits now, its Smart factor and the decision behind it,
its recent 429s; which tiers Smart is shedding; the counter mode and the slots kept for P0 (this process).

The rows are read afresh (not this process's policy view, which may be ``controller.state_refresh_seconds`` old), so
the page shows what was just saved. Nothing here computes a limit of its own: ``rules.limits`` does, as for the
limiter.
"""

from dataclasses import dataclass, replace

from django.conf import settings

from apps.core.models import RequestRateLimitPolicy, RequestRateLimitState

from .limiter import live_processes
from .rules.limits import P0, admission_limit, effective_limits
from .runtime import context, refusals, registry, signals, smart, store
from .runtime.context import section

TIER_ORDER = ("p0", "p1", "p2", "p3")
SHEDDING, RECOVERING, FULL, PROTECTED = "shedding", "recovering", "full", "protected"


@dataclass(frozen=True)
class ScopeView:
    scope: str
    tier: str
    identity: str
    # The route scope a per-view limit sits under (it follows that scope's Smart factor), else None.
    parent: str | None
    enabled: bool
    smart: bool
    fixed: bool
    baseline: int
    mode: str
    # The Smart factor applied now (None while Smart is off).
    factor: float | None
    per_identity: int
    global_cap: int | None
    period: int
    # What one process allows with per-process counters (None for a per-view limit, which keeps its own counter).
    per_process: int | None
    # The controller's last change of the factor (the parent's for a per-view limit): action, tier, reasons, at.
    decision: dict
    # The 429s of the last ``refusal_history_minutes`` by who refused them (None for a per-view limit: its view's
    # refusals are counted under the parent).
    refused: dict | None
    # Requests per period from one source without a verified identity (None: no flood ceiling).
    source_cap: int | None = None

    @property
    def sheddable(self) -> bool:
        return self.smart and self.tier != P0 and not self.fixed


def policies() -> dict[str, RequestRateLimitPolicy]:
    """Every scope's policy row, in ``REQUEST_RATE_LIMITS`` order (a missing row is created from its seed)."""
    specs = section("scopes")
    rows = {row.scope: row for row in RequestRateLimitPolicy.objects.filter(scope__in=list(specs))}
    return {scope: rows.get(scope) or RequestRateLimitPolicy.for_scope(scope) for scope in specs}


def _view(config, spec, parent, processes, decision, refused) -> ScopeView:
    if parent is not None:
        config = replace(config, factor=parent.factor if parent.smart else 1.0)
    limits = effective_limits(config)
    return ScopeView(
        scope=config.scope,
        tier=config.tier,
        identity=config.identity,
        parent=spec.get("parent"),
        enabled=config.enabled,
        smart=config.smart,
        fixed=config.fixed,
        baseline=config.baseline,
        mode=limits.mode,
        factor=limits.factor,
        per_identity=limits.per_identity,
        global_cap=limits.global_cap,
        period=limits.period,
        per_process=None if parent is not None else effective_limits(config, processes).per_identity,
        decision=decision,
        refused=refused,
        source_cap=limits.source_cap,
    )


def scope_views(rows: dict[str, RequestRateLimitPolicy], now: float, processes: int) -> dict[str, ScopeView]:
    """Every scope of ``rows`` as it is limited now."""
    specs = section("scopes")
    states = {row.scope: row for row in RequestRateLimitState.objects.filter(scope__in=list(rows))}
    configs = {}
    for scope, policy in rows.items():
        state = states.get(scope)
        if state is not None and not policy.smart_enabled:
            state = None  # Smart off: the factor is held at 1 (registry), whatever the row still holds
        configs[scope] = registry.build(scope, specs[scope], policy, state)
    route_scopes = [scope for scope in rows if "parent" not in specs[scope]]
    recent = refusals.recent(route_scopes, now)
    views = {}
    for scope, config in configs.items():
        parent_name = specs[scope].get("parent")
        parent = configs.get(parent_name) if parent_name else None
        decider = states.get(parent_name or scope)
        decision = dict(decider.last_decision or {}) if decider is not None else {}
        views[scope] = _view(config, specs[scope], parent, processes, decision, recent.get(scope))
    return views


def _tier_state(tier: str, views) -> dict:
    members = [view for view in views if view.tier == tier and view.parent is None]
    below = [view for view in members if view.sheddable and view.factor is not None and view.factor < 1]
    if tier == P0:
        state = PROTECTED
    elif not below:
        state = FULL
    else:
        latest = max(below, key=lambda view: view.decision.get("at") or "")
        state = SHEDDING if latest.decision.get("action") == "shed" else RECOVERING
    return {
        "tier": tier,
        "label": section("tiers")[tier]["label"],
        "state": state,
        "scopes": len(members),
        "below": [view.scope for view in below],
        "lowest": min((view.factor for view in below), default=None),
    }


def slots() -> dict:
    """This process's concurrency slots: how many are in use, each tier's share and the P0-only ones in use."""
    admission, tiers = section("admission"), section("tiers")
    concurrency, reserved_min = admission["concurrency_limit"], admission["p0_reserved_slots"]
    limits = {tier: admission_limit(tier, concurrency, tiers, reserved_min) for tier in TIER_ORDER}
    in_flight = signals.in_flight()
    # Only P0 may hold a slot beyond the largest share another tier may reach (P1's).
    others = max(limits[tier] for tier in TIER_ORDER if tier != P0)
    reserved = concurrency - others
    return {
        "concurrency": concurrency,
        "in_flight": in_flight,
        "tier_limits": limits,
        "p0_reserved": reserved,
        "p0_reserved_in_use": max(0, min(reserved, in_flight - others)),
    }


def overview(rows: dict[str, RequestRateLimitPolicy] | None = None) -> dict:
    """Everything the page and its status refresh show."""
    now = context.clock()
    rows = policies() if rows is None else rows
    mode = store.mode()
    enabled = bool(settings.REQUEST_RATE_LIMITS_ENABLED)
    # A process with the limiter off keeps no heartbeat: it must not count as one sharing the limits.
    processes = live_processes(now) if enabled else 1
    views = scope_views(rows, now, processes)
    return {
        "enabled": enabled,
        "counter_mode": mode,
        "processes": processes,
        "history_minutes": refusals.history_minutes(),
        "slots": slots(),
        "last_assessment": dict(smart.LAST),
        "tiers": [_tier_state(tier, views.values()) for tier in TIER_ORDER],
        "scopes": views,
    }
