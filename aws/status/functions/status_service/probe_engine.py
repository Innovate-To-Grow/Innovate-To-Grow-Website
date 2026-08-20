"""Combine fixed synthetic probes with read-only AWS runtime signals."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlsplit

from .aws_checks import AwsRuntimeChecks
from .constants import COMPONENTS, ComponentSpec
from .dns_checks import run_dns_probe
from .http_probes import run_http_probe
from .tls_checks import run_tls_probe
from .types import CheckResult, ProbeOutcome


class ProbeEngine:
    def __init__(
        self,
        runtime_checks: AwsRuntimeChecks,
        http_runner=run_http_probe,  # noqa: ANN001
        dns_runner=run_dns_probe,  # noqa: ANN001
        tls_runner=run_tls_probe,  # noqa: ANN001
    ):
        self.runtime_checks = runtime_checks
        self.http_runner = http_runner
        self.dns_runner = dns_runner
        self.tls_runner = tls_runner

    def run(self) -> tuple[dict[str, ProbeOutcome], dict[str, Any]]:
        http_by_component: dict[str, list[CheckResult]] = {component.component_id: [] for component in COMPONENTS}
        network_by_component: dict[str, list[CheckResult]] = {component.component_id: [] for component in COMPONENTS}
        with ThreadPoolExecutor(max_workers=16, thread_name_prefix="status-probe") as executor:
            runtime_future = executor.submit(self.runtime_checks.collect)
            alarm_future = executor.submit(self.runtime_checks.alarm_summary)
            stack_future = executor.submit(self.runtime_checks.stack_summary)
            http_futures = {
                executor.submit(self.http_runner, probe): (component.component_id, probe)
                for component in COMPONENTS
                for probe in component.http_probes
            }
            network_futures = {}
            for component in COMPONENTS:
                hostname = urlsplit(component.http_probes[0].url).hostname or ""
                network_futures[executor.submit(self.dns_runner, f"{component.component_id}.dns", hostname)] = (
                    component.component_id,
                    "dns",
                )
                network_futures[executor.submit(self.tls_runner, f"{component.component_id}.tls", hostname)] = (
                    component.component_id,
                    "tls",
                )
            for future in as_completed(http_futures):
                component_id, probe = http_futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = CheckResult(probe.check_id, "http", "unhealthy", "HTTP_PROBE_ERROR")
                http_by_component[component_id].append(result)
            for future in as_completed(network_futures):
                component_id, category = network_futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = CheckResult(
                        f"{component_id}.{category}", category, "unknown", f"{category.upper()}_CHECK_FAILED"
                    )
                network_by_component[component_id].append(result)
            try:
                runtime_by_component = runtime_future.result()
            except Exception:
                runtime_by_component = {
                    component.component_id: (
                        CheckResult(f"{component.component_id}.aws", "aws", "unknown", "AWS_CHECK_ERROR"),
                    )
                    for component in COMPONENTS
                }
            alarm_result = alarm_future.result()
            stack_result = stack_future.result()

        outcomes: dict[str, ProbeOutcome] = {}
        all_safe_checks: list[dict[str, Any]] = []
        for component in COMPONENTS:
            http_results = sorted(http_by_component[component.component_id], key=lambda item: item.check_id)
            runtime_results = list(runtime_by_component.get(component.component_id, ()))
            runtime_results.extend(sorted(network_by_component[component.component_id], key=lambda item: item.check_id))
            outcomes[component.component_id] = _outcome(component, http_results, runtime_results)
            all_safe_checks.extend(result.safe_dict() for result in (*http_results, *runtime_results))

        detail = {
            "probes": all_safe_checks[:100],
            "alarms": alarm_result,
            "stack": stack_result,
        }
        return outcomes, detail


def _outcome(
    component: ComponentSpec,
    http_results: list[CheckResult],
    runtime_results: list[CheckResult],
) -> ProbeOutcome:
    states = {result.state for result in http_results}
    # An explicit maintenance response is authoritative for the component.
    # Parallel liveness/proxy failures are common while maintenance is active
    # and must not turn the maintenance window into an availability incident.
    if "maintenance" in states:
        health = "maintenance"
        availability = "maintenance"
    elif "unhealthy" in states:
        health = "failed"
        availability = "unavailable"
    elif not http_results or "unknown" in states:
        health = "unknown"
        availability = "unknown"
    else:
        health = "healthy"
        availability = "available"

    infra_degraded = any(
        result.affects_public and result.state in {"degraded", "unhealthy", "unknown"} for result in runtime_results
    )
    latencies = [result.latency_ms for result in http_results if result.latency_ms is not None]
    return ProbeOutcome(
        component_id=component.component_id,
        health=health,
        availability=availability,
        infra_degraded=infra_degraded,
        latency_ms=max(latencies) if latencies else None,
        checks=(*http_results, *runtime_results),
    )
