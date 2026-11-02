"""Run the Smart controller lazily on the request path: when this process's signal window has ended, the first
request to finish assesses it, plans the factor changes and writes only the changed scopes' state rows (no
background worker needed). A row another process changed since this one read it is not overwritten (compare and
set on the factor); the view is reloaded instead.
"""

import logging
from dataclasses import replace

from django.db import DatabaseError

from apps.core.models import RequestRateLimitState

from ..rules.controller import Plan, Pressure, assess, plan
from . import registry, signals
from .context import as_datetime, section

logger = logging.getLogger(__name__)

# This process's last assessment, for the admin and the logs.
LAST: dict = {}


def _decision(result: Plan, pressure: Pressure, now: float) -> dict:
    return {
        "pressure": pressure.level,
        "action": result.action,
        "tier": result.tier,
        "reasons": list(pressure.reasons),
        "signals": pressure.values,
        "at": as_datetime(now).isoformat(),
    }


def _apply(result: Plan, decision: dict, current: dict, now: float) -> None:
    cut = result.action == "shed"
    moment = as_datetime(now)
    for scope, factor in result.factors.items():
        old = current[scope]
        fields = {"factor": factor, "factor_changed_at": moment, "last_decision": decision}
        if cut:
            fields["last_cut_at"] = moment
        try:
            updated = RequestRateLimitState.objects.filter(scope=scope, factor=old.factor).update(**fields)
        except DatabaseError:
            logger.warning("request_limits.state_write_failed", exc_info=True)
            continue
        if not updated:
            registry.invalidate()
            continue
        registry.replace(
            replace(old, factor=factor, factor_changed_at=now, last_cut_at=now if cut else old.last_cut_at)
        )
    logger.info(
        "request_limits.smart %s %s %s",
        result.action,
        result.tier,
        {scope: round(factor, 3) for scope, factor in result.factors.items()},
        extra={"request_limits": decision},
    )


def evaluate(now: float) -> Plan | None:
    """Assess the window that just ended, if one did, and apply the plan; return it (None when no window ended)."""
    snapshot = signals.take_if_due(now)
    if snapshot is None:
        return None
    controller = section("controller")
    pressure = assess(snapshot, controller)
    current = registry.configs(now)
    result = plan(
        pressure,
        current.values(),
        snapshot,
        section("tiers"),
        now=now,
        hold_seconds=controller["recovery_hold_seconds"],
    )
    decision = _decision(result, pressure, now)
    LAST.clear()
    LAST.update(decision)
    if result.factors:
        _apply(result, decision, current, now)
    return result
