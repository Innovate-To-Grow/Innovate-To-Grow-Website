from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest
from status_service.constants import COMPONENTS
from status_service.projection import _overall_status, build_public_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "status" / "contracts" / "status-v1.schema.json"
FIXTURES = REPO_ROOT / "status" / "contracts" / "fixtures"


class ProjectionRepository:
    def __init__(self):
        self.sample_starts = []

    def get_system(self, kind):
        assert kind == "CURRENT"
        return {"generatedAt": "2026-08-20T12:00:00Z"}

    def get_current(self, component_id):
        current = {
            "componentId": component_id,
            "status": "operational",
            "checkedAt": "2026-08-20T12:00:00Z",
        }
        if component_id == "production-api":
            current.update(
                {
                    "status": "degraded",
                    "activeIncidentId": "incident-production-api-20260401000000",
                }
            )
        return current

    def list_samples(self, component_id, start_at, _end_at):
        self.sample_starts.append(start_at)
        samples = [{"availability": "available"}]
        if component_id == "production-api":
            samples.extend(
                [
                    {"availability": "unavailable"},
                    {"availability": "maintenance"},
                    {"availability": "unknown"},
                ]
            )
        return samples

    def list_days(self, component_id, _start_date, _end_date):
        if component_id != "production-api":
            return []
        return [
            {
                "date": "2026-08-20",
                "scheduledCount": 3,
                "availableCount": 1,
                "unavailableCount": 1,
                "maintenanceCount": 1,
                "statusMaintenanceCount": 1,
                "statusDegradedCount": 1,
            }
        ]

    def list_incidents(self, _start_at):
        return []

    def get_incident(self, incident_id):
        return {
            "incidentId": incident_id,
            "kind": "incident",
            "state": "investigating",
            "impact": "major_outage",
            "title": "Availability issue affecting Production API",
            "startedAt": "2026-04-01T00:00:00Z",
            "resolvedAt": None,
            "affectedComponentIds": ["production-api"],
        }

    def list_incident_updates(self, _incident_id):
        return []


def test_projection_matches_shared_schema_and_excludes_maintenance_from_uptime():
    snapshot = build_public_snapshot(
        ProjectionRepository(),
        now=datetime(2026, 8, 20, 12, 1, tzinfo=UTC),
    )

    jsonschema.validate(snapshot, _schema(), format_checker=jsonschema.FormatChecker())
    production_api = next(component for component in snapshot["components"] if component["id"] == "production-api")
    assert production_api["uptime"]["hours24"] == 50.0
    assert production_api["uptime"]["days90"] == 50.0
    assert production_api["history"][-1]["maintenanceSampleCount"] == 1
    assert snapshot["summary"]["availability24h"]["maintenanceChecks"] == 1
    assert snapshot["summary"]["availability24h"]["eligibleChecks"] == 6
    assert len(snapshot["components"]) == 5
    assert len(production_api["history"]) == 90
    # Active incidents remain visible even when they began before the 90-day query window.
    assert snapshot["incidents"][0]["startedAt"] == "2026-04-01T00:00:00Z"
    assert snapshot["incidents"][0]["updates"][0]["state"] == "investigating"


def test_stale_snapshot_forces_unknown_overall_without_discarding_last_known_components():
    snapshot = build_public_snapshot(
        ProjectionRepository(),
        now=datetime(2026, 8, 20, 12, 11, tzinfo=UTC),
    )

    assert snapshot["stale"] is True
    assert snapshot["overallStatus"] == "unknown"
    assert snapshot["components"][0]["status"] == "operational"


def test_24_hour_query_excludes_exact_inclusive_lower_boundary():
    repository = ProjectionRepository()

    build_public_snapshot(repository, now=datetime(2026, 8, 20, 12, 0, tzinfo=UTC))

    assert repository.sample_starts == ["2026-08-19T12:00:01Z"] * 5


def test_active_incident_fallback_update_matches_the_persisted_state():
    class MonitoringRepository(ProjectionRepository):
        def get_incident(self, incident_id):
            incident = super().get_incident(incident_id)
            incident["state"] = "monitoring"
            return incident

    snapshot = build_public_snapshot(
        MonitoringRepository(),
        now=datetime(2026, 8, 20, 12, 1, tzinfo=UTC),
    )

    incident = snapshot["incidents"][0]
    assert incident["state"] == "monitoring"
    assert incident["updates"][-1]["state"] == "monitoring"


def test_embedded_incident_timeline_avoids_per_incident_update_queries():
    class EmbeddedTimelineRepository(ProjectionRepository):
        def get_incident(self, incident_id):
            incident = super().get_incident(incident_id)
            incident["updates"] = [
                {
                    "timestamp": incident["startedAt"],
                    "state": "investigating",
                    "message": "Automated monitoring is investigating.",
                }
            ]
            return incident

        def list_incident_updates(self, _incident_id):
            raise AssertionError("embedded timelines must not issue an update query")

    snapshot = build_public_snapshot(
        EmbeddedTimelineRepository(),
        now=datetime(2026, 8, 20, 12, 1, tzinfo=UTC),
    )

    assert snapshot["incidents"][0]["updates"][0]["state"] == "investigating"


def test_incident_projection_bounds_repeated_monitoring_updates():
    class RepeatedTimelineRepository(ProjectionRepository):
        def get_incident(self, incident_id):
            incident = super().get_incident(incident_id)
            incident["state"] = "resolved"
            incident["resolvedAt"] = "2026-08-20T10:30:00Z"
            incident["updates"] = [
                {
                    "timestamp": "2026-08-20T10:05:00Z",
                    "state": "investigating",
                    "message": "Investigating.",
                },
                *[
                    {
                        "timestamp": f"2026-08-20T10:{minute:02d}:00Z",
                        "state": "monitoring",
                        "message": "Monitoring.",
                    }
                    for minute in range(10, 30, 5)
                ],
                {
                    "timestamp": "2026-08-20T10:30:00Z",
                    "state": "resolved",
                    "message": "Resolved.",
                },
            ]
            return incident

        def list_incident_updates(self, _incident_id):
            raise AssertionError("embedded timelines must not issue an update query")

    snapshot = build_public_snapshot(
        RepeatedTimelineRepository(),
        now=datetime(2026, 8, 20, 12, 1, tzinfo=UTC),
    )

    updates = snapshot["incidents"][0]["updates"]
    assert [update["state"] for update in updates] == ["investigating", "monitoring", "resolved"]
    assert updates[1]["timestamp"] == "2026-08-20T10:25:00Z"


def test_confirmed_nonproduction_outage_is_not_hidden_by_unknown_production_probes():
    components = [
        {"id": "production-website", "status": "unknown"},
        {"id": "production-api", "status": "unknown"},
        {"id": "demo-website", "status": "partial_outage"},
        {"id": "demo-api", "status": "operational"},
        {"id": "project-archive", "status": "operational"},
    ]

    assert _overall_status(components) == "partial_outage"


def test_shared_valid_fixture_passes_json_schema_and_semantics():
    document = json.loads((FIXTURES / "valid" / "status-v1-operational.json").read_text())

    _validate_contract(document)


@pytest.mark.parametrize("fixture_path", sorted((FIXTURES / "invalid").glob("*.json")), ids=lambda path: path.stem)
def test_every_shared_invalid_fixture_is_rejected(fixture_path):
    specification = json.loads(fixture_path.read_text())
    base_path = (fixture_path.parent / specification["base"]).resolve()
    document = json.loads(base_path.read_text())
    for mutation in specification["mutations"]:
        _apply_mutation(document, mutation)

    with pytest.raises((jsonschema.ValidationError, ValueError)):
        _validate_contract(document)


def _schema():
    return json.loads(CONTRACT.read_text())


def _validate_contract(document):
    jsonschema.validate(document, _schema(), format_checker=jsonschema.FormatChecker())
    expected_ids = [component.component_id for component in COMPONENTS]
    actual_ids = [component["id"] for component in document["components"]]
    if sorted(actual_ids) != sorted(expected_ids) or len(set(actual_ids)) != len(actual_ids):
        raise ValueError("component ids must be the exact unique public set")
    for component in document["components"]:
        _require_percent_precision(component["uptime"]["hours24"])
        _require_percent_precision(component["uptime"]["days90"])
        dates = [datetime.fromisoformat(day["date"]).date() for day in component["history"]]
        if any((later - earlier).days != 1 for earlier, later in zip(dates, dates[1:], strict=False)):
            raise ValueError("history dates must be consecutive")
        for day in component["history"]:
            _require_percent_precision(day["uptimePercent"])
            _require_percent_precision(day["coveragePercent"])
    availability = document["summary"]["availability24h"]
    _require_percent_precision(availability["percent"])
    _require_percent_precision(availability["monitoringCoveragePercent"])


def _require_percent_precision(value):
    if value is not None and Decimal(str(value)).as_tuple().exponent < -2:
        raise ValueError("percentages must use no more than two decimal places")


def _apply_mutation(document, mutation):
    tokens = [token.replace("~1", "/").replace("~0", "~") for token in mutation["path"].split("/")[1:]]
    parent = document
    for token in tokens[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    key = tokens[-1]
    operation = mutation["op"]
    if operation == "remove":
        if isinstance(parent, list):
            parent.pop(int(key))
        else:
            parent.pop(key)
    elif operation in {"add", "replace"}:
        value = copy.deepcopy(mutation.get("value"))
        if isinstance(parent, list):
            if key == "-":
                parent.append(value)
            elif operation == "add":
                parent.insert(int(key), value)
            else:
                parent[int(key)] = value
        else:
            parent[key] = value
    else:
        raise AssertionError(f"unsupported fixture mutation: {operation}")
