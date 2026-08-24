"""Deterministic debounce and automatic incident state machine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .constants import COMPONENT_BY_ID
from .types import IncidentMutation, ProbeOutcome, StateTransition


def transition_component(
    outcome: ProbeOutcome,
    previous: dict[str, Any] | None,
    checked_at: str,
) -> StateTransition:
    """Apply the two-failure/two-success policy to one component sample."""

    component = COMPONENT_BY_ID[outcome.component_id]
    previous = previous or {}
    failures = int(previous.get("consecutiveFailures", 0))
    successes = int(previous.get("consecutiveSuccesses", 0))
    active_id = previous.get("activeIncidentId")
    active_kind = previous.get("activeIncidentKind")
    active_started = previous.get("activeIncidentStartedAt")
    active_opened = previous.get("activeIncidentOpenedAt")
    active_monitoring = previous.get("activeIncidentMonitoringAt")
    first_failure = previous.get("firstFailureAt")
    mutations: list[IncidentMutation] = []

    if outcome.health == "unknown":
        public_status = "unknown"
        # A monitor gap must not resolve/escalate an incident and must break
        # both consecutive streaks.
        failures = 0
        successes = 0
        first_failure = None
    elif outcome.health == "maintenance":
        failures = 0
        successes = 0
        first_failure = None
        public_status = "maintenance"
        if active_id and active_kind != "maintenance":
            mutations.append(
                _mutation(
                    "resolve",
                    active_id,
                    "incident",
                    "resolved",
                    checked_at,
                    active_started,
                    component,
                    opened_at=active_opened,
                    monitoring_at=active_monitoring,
                )
            )
            active_id = None
            active_kind = None
            active_opened = None
            active_monitoring = None
        if not active_id:
            active_started = checked_at
            active_opened = checked_at
            active_monitoring = None
            active_id = _incident_id(component.component_id, "maintenance", checked_at)
            active_kind = "maintenance"
            mutations.append(
                _mutation(
                    "open",
                    active_id,
                    "maintenance",
                    "investigating",
                    checked_at,
                    checked_at,
                    component,
                    opened_at=active_opened,
                )
            )
    elif outcome.health == "failed":
        failures += 1
        successes = 0
        first_failure = first_failure or checked_at
        if active_id and active_kind == "maintenance":
            # Maintenance is authoritative until two consecutive healthy,
            # non-maintenance observations confirm it has ended.
            public_status = "maintenance"
        elif active_id and active_kind == "incident":
            public_status = _outage_status(component.production_critical)
        elif failures >= 2:
            active_started = first_failure
            active_opened = checked_at
            active_monitoring = None
            active_id = _incident_id(component.component_id, "incident", first_failure)
            active_kind = "incident"
            public_status = _outage_status(component.production_critical)
            mutations.append(
                _mutation(
                    "open",
                    active_id,
                    "incident",
                    "investigating",
                    checked_at,
                    first_failure,
                    component,
                    opened_at=active_opened,
                )
            )
        else:
            public_status = "degraded"
    else:
        failures = 0
        first_failure = None
        successes += 1
        if active_id:
            if successes == 1:
                public_status = "degraded"
                active_monitoring = checked_at
                mutations.append(
                    _mutation(
                        "update",
                        active_id,
                        active_kind,
                        "monitoring",
                        checked_at,
                        active_started,
                        component,
                        opened_at=active_opened,
                        monitoring_at=active_monitoring,
                    )
                )
            else:
                mutations.append(
                    _mutation(
                        "resolve",
                        active_id,
                        active_kind,
                        "resolved",
                        checked_at,
                        active_started,
                        component,
                        opened_at=active_opened,
                        monitoring_at=active_monitoring,
                    )
                )
                active_id = None
                active_kind = None
                active_started = None
                active_opened = None
                active_monitoring = None
                successes = 0
                public_status = "degraded" if outcome.infra_degraded else "operational"
        else:
            active_opened = None
            active_monitoring = None
            successes = 0
            public_status = "degraded" if outcome.infra_degraded else "operational"

    current = {
        "componentId": component.component_id,
        "name": component.name,
        "group": component.group,
        "status": public_status,
        "checkedAt": checked_at,
        "availability": outcome.availability,
        "latencyMs": outcome.latency_ms,
        "consecutiveFailures": failures,
        "consecutiveSuccesses": successes,
        "firstFailureAt": first_failure,
        "activeIncidentId": active_id,
        "activeIncidentKind": active_kind,
        "activeIncidentStartedAt": active_started,
        "activeIncidentOpenedAt": active_opened,
        "activeIncidentMonitoringAt": active_monitoring,
    }
    return StateTransition(
        component_id=component.component_id,
        checked_at=checked_at,
        public_status=public_status,
        availability=outcome.availability,
        latency_ms=outcome.latency_ms,
        current=current,
        incident_mutations=tuple(mutations),
    )


def _outage_status(production_critical: bool) -> str:
    return "major_outage" if production_critical else "partial_outage"


def _incident_id(component_id: str, kind: str, started_at: str) -> str:
    instant = datetime.fromisoformat(started_at.replace("Z", "+00:00")).strftime("%Y%m%d%H%M%S")
    return f"{kind}-{component_id}-{instant}"[:100]


def _mutation(
    action: str,
    incident_id: str,
    kind: str,
    state: str,
    at: str,
    started_at: str | None,
    component: Any,
    *,
    opened_at: str | None = None,
    monitoring_at: str | None = None,
) -> IncidentMutation:
    if kind == "maintenance":
        impact = "maintenance"
    else:
        impact = _outage_status(component.production_critical)
    return IncidentMutation(
        action=action,
        incident_id=incident_id,
        kind=kind,
        state=state,
        at=at,
        started_at=started_at or at,
        impact=impact,
        component_id=component.component_id,
        opened_at=opened_at,
        monitoring_at=monitoring_at,
    )
