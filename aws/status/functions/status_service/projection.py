"""Build the strictly sanitized public StatusSnapshotV1 projection."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .constants import COMPONENTS, PUBLIC_HISTORY_DAYS, PUBLIC_INCIDENT_DAYS, SCHEDULE_SECONDS, STALE_AFTER_SECONDS


def build_public_snapshot(repository, now: datetime | None = None) -> dict[str, Any] | None:  # noqa: ANN001
    now = (now or datetime.now(UTC)).astimezone(UTC)
    system = repository.get_system("CURRENT")
    if not system or not system.get("generatedAt"):
        return None
    generated = _parse(system["generatedAt"])
    stale = (now - generated).total_seconds() > STALE_AFTER_SECONDS
    start_24h = now - timedelta(hours=24)
    first_day = now.date() - timedelta(days=PUBLIC_HISTORY_DAYS - 1)

    components: list[dict[str, Any]] = []
    all_samples: list[dict[str, Any]] = []
    active_incident_ids: set[str] = set()
    for component in COMPONENTS:
        current = repository.get_current(component.component_id)
        if not current:
            current = {
                "status": "unknown",
                "checkedAt": system["generatedAt"],
            }
        elif current.get("activeIncidentId"):
            active_incident_ids.add(str(current["activeIncidentId"]))
        # DynamoDB BETWEEN is inclusive. Advance by one second so an exact
        # sample at now-24h is excluded and each component contributes at most
        # 288 five-minute slots.
        samples = repository.list_samples(component.component_id, _iso(start_24h + timedelta(seconds=1)), _iso(now))
        days = repository.list_days(component.component_id, first_day.isoformat(), now.date().isoformat())
        days_by_date = {item["date"]: item for item in days}
        history = [
            _history_day(first_day + timedelta(days=offset), days_by_date, now) for offset in range(PUBLIC_HISTORY_DAYS)
        ]
        component_24h = _availability(samples)
        component_90d = _availability_from_days(days)
        components.append(
            {
                "id": component.component_id,
                "name": component.name,
                "group": component.group,
                "status": _valid_status(current.get("status")),
                "checkedAt": str(current.get("checkedAt") or system["generatedAt"]),
                "uptime": {
                    "hours24": component_24h["percent"],
                    "days90": component_90d["percent"],
                },
                "history": history,
            }
        )
        all_samples.extend(samples)

    cutoff = _iso(now - timedelta(days=PUBLIC_INCIDENT_DAYS))
    incident_items = repository.list_incidents(cutoff)
    known_incident_ids = {str(item.get("incidentId", "")) for item in incident_items}
    for incident_id in active_incident_ids - known_incident_ids:
        active_item = repository.get_incident(incident_id)
        if active_item:
            incident_items.append(active_item)
    incidents = [_public_incident(repository, item) for item in incident_items]
    incidents = [incident for incident in incidents if incident is not None]
    incidents.sort(key=lambda item: item["startedAt"], reverse=True)
    availability_24h = _availability(all_samples)
    expected_checks = (24 * 60 * 60 // SCHEDULE_SECONDS) * len(COMPONENTS)
    known_checks = availability_24h["eligibleChecks"] + availability_24h["maintenanceChecks"]
    availability_24h["scheduledChecks"] = expected_checks
    availability_24h["monitoringCoveragePercent"] = _percent(known_checks, expected_checks)

    overall = "unknown" if stale else _overall_status(components)
    active = [incident for incident in incidents if incident["state"] != "resolved"]
    cutoff_24 = _iso(start_24h)
    summary = {
        "message": _overall_message(overall, stale),
        "availability24h": availability_24h,
        "activeIncidentCount": len(active),
        "incidents24h": sum(1 for incident in incidents if incident["startedAt"] >= cutoff_24),
    }
    return {
        "schemaVersion": 1,
        "generatedAt": _iso(generated),
        "nextCheckAt": _iso(generated + timedelta(seconds=SCHEDULE_SECONDS)),
        "stale": stale,
        "overallStatus": overall,
        "summary": summary,
        "components": components,
        "incidents": incidents,
    }


def _history_day(day: date, items: dict[str, dict[str, Any]], now: datetime) -> dict[str, Any]:
    item = items.get(day.isoformat(), {})
    scheduled = int(item.get("scheduledCount", 0))
    available = int(item.get("availableCount", 0))
    unavailable = int(item.get("unavailableCount", 0))
    maintenance = int(item.get("maintenanceCount", 0))
    expected = _expected_slots(day, now)
    known = available + unavailable + maintenance
    return {
        "date": day.isoformat(),
        "status": _daily_status(item, known),
        "uptimePercent": _percent(available, available + unavailable),
        "coveragePercent": _percent(known, expected),
        "sampleCount": scheduled,
        "maintenanceSampleCount": maintenance,
    }


def _expected_slots(day: date, now: datetime) -> int:
    if day < now.date():
        return 24 * 60 * 60 // SCHEDULE_SECONDS
    if day > now.date():
        return 0
    midnight = datetime.combine(day, time.min, tzinfo=UTC)
    return min(24 * 60 * 60 // SCHEDULE_SECONDS, int((now - midnight).total_seconds() // SCHEDULE_SECONDS) + 1)


def _daily_status(item: dict[str, Any], known: int) -> str:
    if known == 0:
        return "unknown"
    for status in ("major_outage", "partial_outage", "maintenance", "degraded"):
        if int(item.get(f"status{_pascal(status)}Count", 0)) > 0:
            return status
    return "operational"


def _availability(items: list[dict[str, Any]]) -> dict[str, Any]:
    available = sum(1 for item in items if item.get("availability") == "available")
    unavailable = sum(1 for item in items if item.get("availability") == "unavailable")
    maintenance = sum(1 for item in items if item.get("availability") == "maintenance")
    return {
        "percent": _percent(available, available + unavailable),
        "availableChecks": available,
        "eligibleChecks": available + unavailable,
        "scheduledChecks": len(items),
        "maintenanceChecks": maintenance,
        "monitoringCoveragePercent": _percent(available + unavailable + maintenance, len(items)),
    }


def _availability_from_days(items: list[dict[str, Any]]) -> dict[str, Any]:
    available = sum(int(item.get("availableCount", 0)) for item in items)
    unavailable = sum(int(item.get("unavailableCount", 0)) for item in items)
    return {"percent": _percent(available, available + unavailable)}


def _public_incident(repository, item: dict[str, Any]) -> dict[str, Any] | None:  # noqa: ANN001
    incident_id = str(item.get("incidentId", ""))
    affected = [value for value in item.get("affectedComponentIds", []) if isinstance(value, str)]
    if not incident_id or not affected:
        return None
    incident_state = (
        str(item.get("state")) if item.get("state") in {"investigating", "monitoring", "resolved"} else "investigating"
    )
    embedded_updates = item.get("updates")
    update_items = (
        embedded_updates if isinstance(embedded_updates, list) else repository.list_incident_updates(incident_id)
    )
    updates = []
    for update in update_items:
        if not isinstance(update, dict):
            continue
        state = str(update.get("state", ""))
        if state not in {"investigating", "monitoring", "resolved"}:
            continue
        updates.append(
            {
                "timestamp": str(update.get("timestamp", item.get("startedAt"))),
                "state": state,
                "message": str(update.get("message", "Status updated."))[:500],
            }
        )
    updates = _bounded_incident_updates(updates)
    if not updates:
        updates.append(
            {
                "timestamp": str(item.get("resolvedAt") or item.get("startedAt")),
                "state": incident_state,
                "message": {
                    "investigating": "Automated monitoring is continuing to investigate this status.",
                    "monitoring": "Automated monitoring is confirming the service recovery.",
                    "resolved": "Automated monitoring confirmed that service operation was restored.",
                }[incident_state],
            }
        )
    return {
        "id": incident_id[:100],
        "kind": "maintenance" if item.get("kind") == "maintenance" else "incident",
        "state": incident_state,
        "impact": _valid_status(item.get("impact")),
        "title": str(item.get("title", "Service status update"))[:160],
        "startedAt": str(item.get("startedAt")),
        "resolvedAt": item.get("resolvedAt") or None,
        "affectedComponentIds": list(dict.fromkeys(affected)),
        "updates": updates,
    }


def _bounded_incident_updates(updates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep at most the opening, latest monitoring, and final resolution entries."""

    by_state: dict[str, dict[str, str]] = {}
    for update in sorted(updates, key=lambda value: value["timestamp"]):
        state = update["state"]
        if state == "investigating":
            by_state.setdefault(state, update)
        else:
            by_state[state] = update
    return [by_state[state] for state in ("investigating", "monitoring", "resolved") if state in by_state]


def _overall_status(components: list[dict[str, Any]]) -> str:
    by_id = {component["id"]: component["status"] for component in components}
    statuses = set(by_id.values())
    if "major_outage" in statuses:
        return "major_outage"
    if "partial_outage" in statuses:
        return "partial_outage"
    if all(by_id.get(component_id) == "unknown" for component_id in ("production-website", "production-api")):
        return "unknown"
    if "maintenance" in statuses:
        return "maintenance"
    if statuses & {"degraded", "unknown"}:
        return "degraded"
    return "operational"


def _overall_message(status: str, stale: bool) -> str:
    if stale:
        return "Current status data is delayed. Last-known results are shown below."
    return {
        "operational": "All monitored systems are operational.",
        "degraded": "Some systems are experiencing degraded performance. Automated monitoring is investigating.",
        "partial_outage": "A non-production service is currently unavailable.",
        "major_outage": "A production service is currently unavailable.",
        "maintenance": "Maintenance is currently in progress.",
        "unknown": "Current system status is unavailable.",
    }[status]


def _valid_status(value: Any) -> str:
    if value in {"operational", "degraded", "partial_outage", "major_outage", "maintenance", "unknown"}:
        return str(value)
    return "unknown"


def _percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(min(100.0, max(0.0, numerator * 100.0 / denominator)), 2)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))
