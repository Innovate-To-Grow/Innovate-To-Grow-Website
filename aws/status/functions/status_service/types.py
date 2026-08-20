"""Small typed value objects shared by the status Lambda handlers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CheckState = Literal["healthy", "degraded", "unhealthy", "maintenance", "unknown", "info"]
Availability = Literal["available", "unavailable", "maintenance", "unknown"]


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    category: str
    state: CheckState
    code: str
    latency_ms: int | None = None
    affects_public: bool = True
    detail: dict[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation with no endpoints or raw errors."""

        value = asdict(self)
        value["checkId"] = value.pop("check_id")
        value["latencyMs"] = value.pop("latency_ms")
        value["affectsPublic"] = value.pop("affects_public")
        return value


@dataclass(frozen=True)
class ProbeOutcome:
    component_id: str
    health: Literal["healthy", "failed", "maintenance", "unknown"]
    availability: Availability
    infra_degraded: bool
    latency_ms: int | None
    checks: tuple[CheckResult, ...]


@dataclass(frozen=True)
class IncidentMutation:
    action: Literal["open", "update", "resolve"]
    incident_id: str
    kind: Literal["incident", "maintenance"]
    state: Literal["investigating", "monitoring", "resolved"]
    at: str
    started_at: str
    impact: Literal["degraded", "partial_outage", "major_outage", "maintenance"]
    component_id: str
    opened_at: str | None = None
    monitoring_at: str | None = None


@dataclass(frozen=True)
class StateTransition:
    component_id: str
    checked_at: str
    public_status: str
    availability: Availability
    latency_ms: int | None
    current: dict[str, Any]
    incident_mutations: tuple[IncidentMutation, ...]
