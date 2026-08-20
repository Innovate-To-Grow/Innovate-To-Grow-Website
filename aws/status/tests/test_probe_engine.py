from __future__ import annotations

from status_service.constants import COMPONENTS
from status_service.probe_engine import ProbeEngine
from status_service.types import CheckResult


class RuntimeChecks:
    def __init__(self, checks=None):
        self.checks = checks or {component.component_id: () for component in COMPONENTS}

    def collect(self):
        return self.checks

    def alarm_summary(self):
        return {"state": "ok", "alarms": []}

    def stack_summary(self):
        return {"state": "ok", "name": "i2g-status", "resources": []}


def healthy_http(spec):
    if spec.check_id == "project-archive.readiness":
        return CheckResult(spec.check_id, "http", "unhealthy", "HEALTH_NOT_OK", 20)
    return CheckResult(spec.check_id, "http", "healthy", "HEALTH_OK", 10)


def healthy_network(check_id, _hostname):
    category = check_id.rsplit(".", 1)[-1]
    return CheckResult(check_id, category, "healthy", f"{category.upper()}_OK")


def test_archive_readiness_failure_alone_only_fails_archive():
    outcomes, _detail = ProbeEngine(
        RuntimeChecks(),
        http_runner=healthy_http,
        dns_runner=healthy_network,
        tls_runner=healthy_network,
    ).run()

    assert outcomes["project-archive"].health == "failed"
    assert outcomes["project-archive"].availability == "unavailable"
    assert all(
        outcome.health == "healthy" for component_id, outcome in outcomes.items() if component_id != "project-archive"
    )


def test_single_aws_source_unknown_degrades_healthy_user_path():
    checks = {component.component_id: () for component in COMPONENTS}
    checks["production-website"] = (CheckResult("production-website.amplify", "aws", "unknown", "AWS_CHECK_ERROR"),)
    engine = ProbeEngine(
        RuntimeChecks(checks),
        http_runner=lambda spec: CheckResult(spec.check_id, "http", "healthy", "HTTP_OK", 5),
        dns_runner=healthy_network,
        tls_runner=healthy_network,
    )

    outcomes, _detail = engine.run()

    assert outcomes["production-website"].health == "healthy"
    assert outcomes["production-website"].availability == "available"
    assert outcomes["production-website"].infra_degraded is True


def test_explicit_maintenance_wins_over_parallel_http_failure():
    def maintenance_http(spec):
        if spec.check_id == "production-api.readiness":
            return CheckResult(spec.check_id, "http", "maintenance", "MAINTENANCE_ACTIVE", 5)
        if spec.check_id == "production-api.liveness":
            return CheckResult(spec.check_id, "http", "unhealthy", "HTTP_TIMEOUT", 5)
        return CheckResult(spec.check_id, "http", "healthy", "HTTP_OK", 5)

    outcomes, _detail = ProbeEngine(
        RuntimeChecks(),
        http_runner=maintenance_http,
        dns_runner=healthy_network,
        tls_runner=healthy_network,
    ).run()

    assert outcomes["production-api"].health == "maintenance"
    assert outcomes["production-api"].availability == "maintenance"
