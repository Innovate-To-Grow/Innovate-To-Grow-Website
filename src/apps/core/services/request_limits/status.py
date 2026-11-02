"""The live request-limit state of this process, for the admin page and the logs."""

from .limiter import live_processes
from .rules.limits import admission_limit, effective_limits
from .runtime import context, registry, signals, smart, store
from .runtime.context import section


def counter_mode() -> str:
    """``shared`` (one atomic counter for every process) or ``local`` (per process, limits ÷ live processes)."""
    return store.mode()


def runtime_status() -> dict:
    """Counter mode, processes, slots, the last Smart decision and every scope's limits as this process sees them."""
    now = context.clock()
    processes = live_processes(now)
    admission, tiers = section("admission"), section("tiers")
    slots = admission["concurrency_limit"]
    scopes = []
    for config in registry.configs(now).values():
        limits = effective_limits(config)
        scopes.append(
            {
                "scope": config.scope,
                "label": config.label,
                "tier": config.tier,
                "enabled": config.enabled,
                "mode": limits.mode,
                "factor": limits.factor,
                "per_identity": limits.per_identity,
                "global_cap": limits.global_cap,
                "period_seconds": limits.period,
                "per_process": effective_limits(config, processes).per_identity,
            }
        )
    return {
        "counter_mode": store.mode(),
        "processes": processes,
        "in_flight": signals.in_flight(),
        "slots": {tier: admission_limit(tier, slots, tiers, admission["p0_reserved_slots"]) for tier in tiers},
        "last_decision": dict(smart.LAST),
        "scopes": scopes,
    }
