from __future__ import annotations

from status_service.state_machine import transition_component
from status_service.types import ProbeOutcome


def outcome(health: str, availability: str, *, component_id="production-api", infra=False):
    return ProbeOutcome(component_id, health, availability, infra, 12, ())


def step(probe, previous, minute):
    return transition_component(probe, previous, f"2026-08-20T10:{minute:02d}:00Z")


def test_two_failures_open_incident_and_two_successes_resolve_it():
    first = step(outcome("failed", "unavailable"), None, 0)
    second = step(outcome("failed", "unavailable"), first.current, 5)
    recovering = step(outcome("healthy", "available"), second.current, 10)
    recovered = step(outcome("healthy", "available"), recovering.current, 15)

    assert first.public_status == "degraded"
    assert first.incident_mutations == ()
    assert second.public_status == "major_outage"
    assert second.incident_mutations[0].action == "open"
    assert second.incident_mutations[0].started_at == "2026-08-20T10:00:00Z"
    assert recovering.public_status == "degraded"
    assert recovering.incident_mutations[0].state == "monitoring"
    assert recovered.public_status == "operational"
    assert recovered.incident_mutations[0].state == "resolved"


def test_unknown_breaks_failure_and_recovery_streaks_without_closing_incident():
    first_failure = step(outcome("failed", "unavailable"), None, 0)
    gap = step(outcome("unknown", "unknown"), first_failure.current, 5)
    failure_after_gap = step(outcome("failed", "unavailable"), gap.current, 10)
    outage = step(outcome("failed", "unavailable"), failure_after_gap.current, 15)
    first_recovery = step(outcome("healthy", "available"), outage.current, 20)
    recovery_gap = step(outcome("unknown", "unknown"), first_recovery.current, 25)
    recovery_after_gap = step(outcome("healthy", "available"), recovery_gap.current, 30)

    assert failure_after_gap.public_status == "degraded"
    assert failure_after_gap.incident_mutations == ()
    assert recovery_gap.current["activeIncidentId"] == outage.current["activeIncidentId"]
    assert recovery_after_gap.public_status == "degraded"
    assert recovery_after_gap.incident_mutations[0].state == "monitoring"


def test_maintenance_is_immediate_excluded_and_requires_two_healthy_results_to_end():
    maintenance = step(outcome("maintenance", "maintenance"), None, 0)
    failed_once = step(outcome("failed", "unavailable"), maintenance.current, 5)
    failed_twice = step(outcome("failed", "unavailable"), failed_once.current, 10)
    healthy_once = step(outcome("healthy", "available"), failed_twice.current, 15)
    healthy_twice = step(outcome("healthy", "available"), healthy_once.current, 20)

    assert maintenance.public_status == "maintenance"
    assert maintenance.availability == "maintenance"
    assert maintenance.incident_mutations[0].kind == "maintenance"
    assert failed_once.public_status == "maintenance"
    assert failed_twice.current["activeIncidentKind"] == "maintenance"
    assert all(
        mutation.action != "resolve" for mutation in (*failed_once.incident_mutations, *failed_twice.incident_mutations)
    )
    assert healthy_once.incident_mutations[0].state == "monitoring"
    assert healthy_twice.incident_mutations[0].state == "resolved"


def test_healthy_user_path_with_bad_internal_signal_is_available_but_degraded():
    result = step(outcome("healthy", "available", infra=True), None, 0)

    assert result.public_status == "degraded"
    assert result.availability == "available"


def test_repeated_recovery_attempts_keep_only_the_latest_monitoring_timestamp():
    first_failure = step(outcome("failed", "unavailable"), None, 0)
    outage = step(outcome("failed", "unavailable"), first_failure.current, 5)
    first_monitoring = step(outcome("healthy", "available"), outage.current, 10)
    failed_again = step(outcome("failed", "unavailable"), first_monitoring.current, 15)
    latest_monitoring = step(outcome("healthy", "available"), failed_again.current, 20)
    resolved = step(outcome("healthy", "available"), latest_monitoring.current, 25)

    assert first_monitoring.current["activeIncidentMonitoringAt"] == "2026-08-20T10:10:00Z"
    assert latest_monitoring.current["activeIncidentMonitoringAt"] == "2026-08-20T10:20:00Z"
    assert resolved.incident_mutations[0].monitoring_at == "2026-08-20T10:20:00Z"
    assert resolved.current["activeIncidentMonitoringAt"] is None
