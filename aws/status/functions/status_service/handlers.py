"""Lambda entry points for probing and public/internal status reads."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from .aws_checks import AwsRuntimeChecks
from .constants import COMPONENTS
from .probe_engine import ProbeEngine
from .projection import build_public_snapshot
from .repository import StatusRepository
from .settings import Settings
from .state_machine import transition_component

PUBLIC_CACHE_CONTROL = "public,max-age=60,s-maxage=60,stale-if-error=900"
PRIVATE_CACHE_CONTROL = "private,no-store"


def probe_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    try:
        slot_at = _scheduled_time(event.get("time")) if event.get("time") else None
        return run_probe(slot_at=slot_at)
    except Exception:
        # Never let provider exception text, ARNs, account IDs, or response bodies
        # leak into Lambda's uncaught-exception log line.
        raise RuntimeError("STATUS_PROBE_FAILED") from None


def run_probe(
    *,
    now: datetime | None = None,
    slot_at: datetime | None = None,
    settings: Settings | None = None,
    repository: StatusRepository | None = None,
    engine: ProbeEngine | None = None,
    metric_writer: Any | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    settings = settings or Settings.from_env()
    repository = repository or StatusRepository(settings.table_name)
    runtime_checks = None
    if engine is None:
        runtime_checks = AwsRuntimeChecks(settings)
        engine = ProbeEngine(runtime_checks)
    if metric_writer is None:
        try:
            metric_writer = _CloudWatchMetrics(settings.aws_region)
        except Exception:
            metric_writer = None
    generated_at = _iso(now)
    slot_source = (slot_at or now).astimezone(UTC)
    if slot_at is not None and (slot_source > now + timedelta(minutes=1) or slot_source < now - timedelta(minutes=20)):
        raise ValueError("scheduled timestamp outside the accepted delivery window")
    slot_time = slot_source.replace(second=0, microsecond=0, minute=slot_source.minute - slot_source.minute % 5)
    checked_at = _iso(slot_time)
    slot = slot_time.strftime("%Y%m%dT%H%MZ")

    if not repository.begin_run(slot, generated_at):
        return {"status": "duplicate", "slot": slot}

    try:
        outcomes, probe_detail = engine.run()
        saved = 0
        for component in COMPONENTS:
            outcome = outcomes[component.component_id]
            previous = repository.get_current(component.component_id)
            transition = transition_component(outcome, previous, checked_at)
            if repository.save_transition(transition):
                saved += 1

        services = []
        for component in COMPONENTS:
            current = repository.get_current(component.component_id) or {
                "componentId": component.component_id,
                "name": component.name,
                "group": component.group,
                "status": "unknown",
                "checkedAt": checked_at,
            }
            services.append(_internal_service(current))

        checks = probe_detail.get("probes", [])[:100]
        alarm_result = probe_detail.get("alarms", {})
        errors = _detail_errors(checks, alarm_result)
        stack_result = probe_detail.get("stack", {})
        if stack_result.get("state") == "partial":
            errors.append({"source": "stack", "code": str(stack_result.get("code", "STACK_UNAVAILABLE"))[:80]})
        internal_detail = {
            "schemaVersion": 1,
            "partial": bool(errors),
            "errors": errors,
            "stack": {
                "name": str(stack_result.get("name", settings.stack_name))[:128],
                "region": settings.aws_region,
                "stackStatus": str(stack_result.get("stackStatus", "UNKNOWN"))[:80],
                "version": settings.release_sha,
                "resources": [item for item in stack_result.get("resources", []) if isinstance(item, dict)][:250],
            },
            "services": _build_internal_services(services, checks, settings),
            "probes": _build_internal_probes(services, checks),
            "alarms": list(alarm_result.get("alarms", []))[:200],
            "releaseSha": settings.release_sha,
        }
        repository.put_system_snapshots(
            generated_at,
            checked_at,
            {"releaseSha": settings.release_sha, "componentCount": len(COMPONENTS)},
            internal_detail,
        )
        repository.finish_run(slot, "COMPLETE", generated_at)
        _publish_metric(metric_writer, 1)
        return {"status": "complete", "slot": slot, "componentsSaved": saved}
    except Exception:
        repository.finish_run(slot, "FAILED", generated_at)
        _publish_metric(metric_writer, 0)
        raise


def public_read_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del event, context
    try:
        snapshot = build_public_snapshot(StatusRepository(os.environ["STATUS_TABLE_NAME"]))
        if snapshot is None:
            return _response(
                503,
                {"error": "STATUS_INITIALIZING", "message": "Status data is not available yet."},
                cache_control="no-store",
                extra_headers={"Retry-After": "60"},
            )
        return _response(200, snapshot, cache_control=PUBLIC_CACHE_CONTROL)
    except Exception:
        return _response(
            503,
            {"error": "STATUS_UNAVAILABLE", "message": "Status data is temporarily unavailable."},
            cache_control="no-store",
            extra_headers={"Retry-After": "60"},
        )


def internal_read_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del event, context
    try:
        detail = StatusRepository(os.environ["STATUS_TABLE_NAME"]).get_system("DETAIL")
        if not detail:
            return _response(
                503,
                {"error": "STATUS_INITIALIZING", "message": "Infrastructure status is not available yet."},
                cache_control=PRIVATE_CACHE_CONTROL,
                extra_headers={"Retry-After": "60"},
            )
        payload = _sanitize_internal(detail)
        return _response(200, payload, cache_control=PRIVATE_CACHE_CONTROL)
    except Exception:
        return _response(
            503,
            {"error": "STATUS_UNAVAILABLE", "message": "Infrastructure status is temporarily unavailable."},
            cache_control=PRIVATE_CACHE_CONTROL,
            extra_headers={"Retry-After": "60"},
        )


def _sanitize_internal(detail: dict[str, Any]) -> dict[str, Any]:
    generated_at = str(detail.get("generatedAt", ""))
    errors = [error for error in detail.get("errors", []) if isinstance(error, dict)][:20]
    partial = bool(detail.get("partial", False))
    try:
        if datetime.now(UTC) - datetime.fromisoformat(generated_at.replace("Z", "+00:00")) > timedelta(minutes=10):
            partial = True
            errors.append({"source": "monitor", "code": "MONITOR_STALE"})
    except ValueError:
        partial = True
        errors.append({"source": "monitor", "code": "MONITOR_TIMESTAMP_INVALID"})
    stack = detail.get("stack", {}) if isinstance(detail.get("stack"), dict) else {}
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "partial": partial,
        "errors": errors[:20],
        "stack": {
            "name": str(stack.get("name", "i2g-status"))[:128],
            "region": str(stack.get("region", "us-west-2"))[:40],
            "stackStatus": str(stack.get("stackStatus", "UNKNOWN"))[:80],
            "version": str(stack.get("version", "unknown"))[:64],
            "resources": [item for item in stack.get("resources", []) if isinstance(item, dict)][:250],
        },
        "services": [item for item in detail.get("services", []) if isinstance(item, dict)][:50],
        "probes": [item for item in detail.get("probes", []) if isinstance(item, dict)][:100],
        "alarms": [item for item in detail.get("alarms", []) if isinstance(item, dict)][:200],
    }


def _internal_service(current: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(current.get("componentId", ""))[:80],
        "name": str(current.get("name", ""))[:80],
        "group": str(current.get("group", ""))[:40],
        "status": str(current.get("status", "unknown"))[:40],
        "checkedAt": str(current.get("checkedAt", ""))[:40],
        "latencyMs": current.get("latencyMs"),
        "consecutiveFailures": int(current.get("consecutiveFailures", 0)),
    }


def _build_internal_services(
    currents: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    settings: Settings,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for current in currents:
        component_id = str(current.get("id", ""))
        component_checks = [
            check
            for check in checks
            if str(check.get("checkId", "")).startswith(f"{component_id}.")
            or (check.get("checkId") == "shared.database" and component_id in {"production-api", "demo-api"})
        ]
        aws_detail: dict[str, Any] = {}
        dependencies: list[dict[str, Any]] = []
        for check in component_checks:
            check_id = str(check.get("checkId", ""))
            detail = check.get("detail", {}) if isinstance(check.get("detail"), dict) else {}
            if check_id.endswith(".compute"):
                aws_detail["ecs"] = {
                    "cluster": detail.get("cluster", settings.ecs_cluster_name),
                    "service": detail.get("service"),
                    "taskDefinition": detail.get("taskDefinition"),
                    "desired": detail.get("desiredTasks"),
                    "running": detail.get("runningTasks"),
                    "pending": detail.get("pendingTasks"),
                    "deployments": list(detail.get("deployments", []))[:10],
                }
            elif check_id.endswith(".load-balancer"):
                aws_detail["loadBalancer"] = {
                    "name": f"{component_id} target group",
                    "targetHealth": list(detail.get("targetHealth", []))[:20],
                }
            elif check_id.endswith(".amplify"):
                aws_detail["amplify"] = {
                    "appId": detail.get("appId"),
                    "branch": detail.get("branch"),
                    "lastJob": detail.get("lastJob", {}),
                }
            elif check.get("category") in {"aws", "dns", "tls"}:
                dependencies.append(
                    {
                        "type": check_id.rsplit(".", 1)[-1],
                        "id": check_id,
                        "status": _internal_outcome(str(check.get("state", "unknown"))),
                    }
                )
        if dependencies:
            aws_detail["dependencies"] = dependencies[:20]
        rows.append(
            {
                "id": component_id,
                "name": str(current.get("name", component_id))[:80],
                "environment": str(current.get("group", ""))[:40],
                "summaryStatus": str(current.get("status", "unknown"))[:40],
                "publicComponentId": component_id,
                "aws": aws_detail,
            }
        )
    return rows[:50]


def _build_internal_probes(
    currents: list[dict[str, Any]],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_by_id = {str(item.get("id", "")): item for item in currents}
    probes = []
    for check in checks:
        if check.get("category") != "http":
            continue
        check_id = str(check.get("checkId", ""))[:100]
        component_id = check_id.split(".", 1)[0]
        current = current_by_id.get(component_id, {})
        code = str(check.get("code", ""))[:80]
        http_status = _http_status(code, str(check.get("state", "")))
        probes.append(
            {
                "componentId": check_id,
                "expected": 200,
                "last": {
                    "checkedAt": str(current.get("checkedAt", ""))[:40],
                    "httpStatus": http_status,
                    "latencyMs": check.get("latencyMs"),
                    "outcome": _internal_outcome(str(check.get("state", "unknown"))),
                    "errorCode": "" if check.get("state") in {"healthy", "maintenance"} else code,
                },
                "consecutiveFailures": int(current.get("consecutiveFailures", 0)),
                "consecutiveSuccesses": 0 if int(current.get("consecutiveFailures", 0)) else 1,
            }
        )
    return probes[:100]


def _internal_outcome(state: str) -> str:
    return {
        "healthy": "operational",
        "info": "operational",
        "maintenance": "maintenance",
        "degraded": "degraded",
        "unhealthy": "major_outage",
        "unknown": "unknown",
    }.get(state, "unknown")


def _http_status(code: str, state: str) -> int | None:
    if code.startswith("HTTP_") and code[5:].isdigit():
        return int(code[5:])
    if state in {"healthy", "maintenance"}:
        return 200
    return None


def _detail_errors(checks: list[dict[str, Any]], alarm_result: dict[str, Any]) -> list[dict[str, str]]:
    errors = [
        {"source": str(check.get("checkId", "probe"))[:100], "code": str(check.get("code", "UNKNOWN"))[:80]}
        for check in checks
        if check.get("state") == "unknown"
    ]
    if alarm_result.get("state") == "partial":
        errors.append({"source": "alarms", "code": str(alarm_result.get("code", "ALARMS_UNAVAILABLE"))[:80]})
    return errors[:20]


def _response(
    status_code: int,
    payload: dict[str, Any],
    *,
    cache_control: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
    }
    headers.update(extra_headers or {})
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _scheduled_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid scheduler timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("scheduler timestamp must be UTC")
    return parsed.astimezone(UTC)


def _publish_metric(metric_writer: Any, value: int) -> None:
    try:
        metric_writer.success(value)
    except Exception:
        # Metrics are observability, not part of the committed monitor transaction.
        return


class _CloudWatchMetrics:
    def __init__(self, region: str):
        import boto3

        self.client = boto3.client("cloudwatch", region_name=region)

    def success(self, value: int) -> None:
        self.client.put_metric_data(
            Namespace="I2G/Status",
            MetricData=[{"MetricName": "ProbeSuccess", "Value": value, "Unit": "Count"}],
        )
