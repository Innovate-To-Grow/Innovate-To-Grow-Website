#!/usr/bin/env python3
"""Validate the production/demo backend ECS task topology before rollout."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

WEB_CONTAINER = "itg-backend"
WORKER_CONTAINER = "itg-background-worker"
WORKER_ENTRYPOINT = ["python"]
WORKER_COMMAND = [
    "manage.py",
    "run_background_worker",
    "--settings=config.settings.production",
]
REQUIRED_SHARED_ENV = {
    "DJANGO_SETTINGS_MODULE",
    "DB_NAME",
    "DB_USER",
    "DB_HOST",
    "DB_PORT",
    "AWS_REGION",
    "AMPLIFY_APP_ID",
    "AMPLIFY_BACKEND_PROXY_URL",
    "AMPLIFY_PROXY_ADMIN_PATHS",
    "AMPLIFY_CONFIG_REVISION",
    "BACKGROUND_JOBS_ENABLED",
    "LEGACY_VIEW_ENABLED",
    "LEGACY_ORIGIN_URL",
    "LEGACY_VIEWER_URL",
    "LEGACY_ORIGIN_HEADER_NAME",
    "LEGACY_CONNECT_TIMEOUT_SECONDS",
    "LEGACY_READ_TIMEOUT_SECONDS",
}
REQUIRED_SHARED_SECRETS = {"DJANGO_SECRET_KEY", "DB_PASSWORD"}
# Secrets that authenticate inbound HTTP and must never reach the worker.
WEB_ONLY_SECRETS = {"LEGACY_ORIGIN_HEADER_VALUE"}
SECRET_ARN_PREFIXES = ("arn:aws:secretsmanager:", "arn:aws:ssm:")
TRUE_VALUES = {"1", "true", "yes", "on"}
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
CLOUDFRONT_HOST_RE = re.compile(r"^d[a-z0-9]+\.cloudfront\.net$")
LEGACY_TIMEOUT_LIMITS = {"LEGACY_CONNECT_TIMEOUT_SECONDS": 30.0, "LEGACY_READ_TIMEOUT_SECONDS": 120.0}
PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")
AMPLIFY_CONFIG_REVISION_RE = re.compile(r"^[1-9][0-9]*\.[1-9][0-9]*$")


class TaskDefinitionValidationError(ValueError):
    """The task definition cannot safely run the web/worker topology."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TaskDefinitionValidationError(message)


def _environment(container: dict[str, Any]) -> dict[str, str]:
    items = container.get("environment") or []
    names = [str(item.get("name") or "") for item in items]
    _require(len(names) == len(set(names)), f"{container.get('name')} has duplicate environment names.")
    return {str(item["name"]): str(item.get("value") or "") for item in items}


def _secrets(container: dict[str, Any]) -> dict[str, str]:
    items = container.get("secrets") or []
    names = [str(item.get("name") or "") for item in items]
    _require(len(names) == len(set(names)), f"{container.get('name')} has duplicate secret names.")
    return {str(item["name"]): str(item.get("valueFrom") or "") for item in items}


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def _validate_legacy_view(env: dict[str, str], secrets: dict[str, str]) -> None:
    """Reject rendered Legacy viewer settings the runbook forbids."""

    for name, maximum in LEGACY_TIMEOUT_LIMITS.items():
        try:
            timeout = float(env[name])
        except ValueError:
            timeout = -1.0
        _require(0.1 <= timeout <= maximum, f"{name} must be between 0.1 and {maximum:g} seconds.")

    origin_url = env["LEGACY_ORIGIN_URL"].strip()
    if origin_url:
        try:
            origin = urlsplit(origin_url)
            origin_port = origin.port
            origin_ip = ipaddress.ip_address(origin.hostname or "")
        except ValueError:
            origin, origin_port, origin_ip = None, None, None
        _require(
            origin is not None
            and origin.scheme == "http"
            and origin_ip is not None
            and origin_ip.is_private
            and origin_port is not None
            and not (origin.username or origin.password or origin.query or origin.fragment)
            and origin.path in {"", "/"},
            "LEGACY_ORIGIN_URL must be a private http://<ip>:<port> origin without a path.",
        )

    viewer_url = env["LEGACY_VIEWER_URL"].strip()
    if viewer_url:
        try:
            viewer = urlsplit(viewer_url)
            viewer_port = viewer.port
        except ValueError:
            viewer, viewer_port = None, None
        _require(
            viewer is not None
            and viewer.scheme == "https"
            and bool(CLOUDFRONT_HOST_RE.fullmatch((viewer.hostname or "").lower()))
            and viewer_port in {None, 443}
            and not (viewer.username or viewer.password or viewer.query or viewer.fragment)
            and viewer.path in {"", "/"},
            "LEGACY_VIEWER_URL must be an HTTPS *.cloudfront.net origin without a path.",
        )

    header_name = env["LEGACY_ORIGIN_HEADER_NAME"].strip()
    if header_name:
        _require(bool(HEADER_NAME_RE.fullmatch(header_name)), "LEGACY_ORIGIN_HEADER_NAME is not a valid header name.")

    if env["LEGACY_VIEW_ENABLED"].strip().lower() in TRUE_VALUES:
        _require(
            bool(origin_url and viewer_url and header_name and "LEGACY_ORIGIN_HEADER_VALUE" in secrets),
            "An enabled Legacy viewer requires its origin URL, CloudFront viewer URL, header name, and header secret.",
        )


def validate_task_definition(taskdef: dict[str, Any], *, rendered: bool) -> None:
    """Raise when the backend task cannot safely start both processes."""

    _require(taskdef.get("networkMode") == "awsvpc", "Backend task must use awsvpc networking.")
    _require("FARGATE" in (taskdef.get("requiresCompatibilities") or []), "Backend task must support Fargate.")

    containers = {
        str(container.get("name") or ""): container for container in taskdef.get("containerDefinitions") or []
    }
    _require(WEB_CONTAINER in containers, f"Missing {WEB_CONTAINER} container.")
    _require(WORKER_CONTAINER in containers, f"Missing {WORKER_CONTAINER} container.")
    web = containers[WEB_CONTAINER]
    worker = containers[WORKER_CONTAINER]

    _require(web.get("essential") is True, "Web container must remain essential.")
    _require(worker.get("essential") is True, "Background worker must be essential so ECS replaces it after exit.")
    _require(web.get("image") == worker.get("image"), "Web and worker must use the same immutable image.")
    _require(
        any(int(mapping.get("containerPort", 0)) == 8000 for mapping in web.get("portMappings") or []),
        "Web container must expose port 8000.",
    )
    _require(not (worker.get("portMappings") or []), "Background worker must not expose a network port.")
    _require(bool(web.get("healthCheck")), "Web container needs the liveness health check used by ECS.")
    _require(not worker.get("healthCheck"), "Worker must not reuse the Web HTTP health check.")

    _require(
        worker.get("entryPoint") == WORKER_ENTRYPOINT,
        "Worker entryPoint must override the image's Web/migration entrypoint.",
    )
    _require(worker.get("command") == WORKER_COMMAND, "Worker command must run the durable management command.")
    dependencies = worker.get("dependsOn") or []
    _require(
        {"containerName": WEB_CONTAINER, "condition": "HEALTHY"} in dependencies,
        "Worker must wait for Web health so startup migrations finish first.",
    )
    _require(int(worker.get("stopTimeout", 0)) >= 120, "Worker needs the Fargate maximum graceful stop window.")

    task_cpu = int(taskdef.get("cpu") or 0)
    task_memory = int(taskdef.get("memory") or 0)
    web_cpu = int(web.get("cpu") or 0)
    worker_cpu = int(worker.get("cpu") or 0)
    web_memory = int(web.get("memoryReservation") or 0)
    worker_memory = int(worker.get("memoryReservation") or 0)
    _require(task_cpu >= 1024, "Web plus worker requires at least 1 vCPU at task level.")
    _require(task_memory >= 2048, "Web plus worker requires at least 2 GiB at task level.")
    _require(web_cpu >= 768, "Web container requires at least 768 CPU units.")
    _require(worker_cpu >= 256, "Background worker requires at least 256 CPU units.")
    _require(web_memory >= 1024, "Web container requires at least a 1 GiB memory reservation.")
    _require(worker_memory >= 512, "Background worker requires at least a 512 MiB memory reservation.")
    _require(web_cpu >= worker_cpu * 3, "Web must retain at least a 3:1 CPU share over the worker.")
    _require(web_cpu + worker_cpu <= task_cpu, "Container CPU shares exceed task CPU.")
    _require(web_memory + worker_memory <= task_memory, "Container memory reservations exceed task memory.")

    web_log_options = (web.get("logConfiguration") or {}).get("options") or {}
    worker_log_options = (worker.get("logConfiguration") or {}).get("options") or {}
    _require(web_log_options.get("awslogs-group"), "Web CloudWatch log group is missing.")
    _require(worker_log_options.get("awslogs-group"), "Worker CloudWatch log group is missing.")
    _require(
        web_log_options.get("awslogs-group") == worker_log_options.get("awslogs-group"),
        "Web and worker must write to the same environment-specific CloudWatch log group.",
    )
    _require(
        web_log_options.get("awslogs-stream-prefix") != worker_log_options.get("awslogs-stream-prefix"),
        "Web and worker need distinct CloudWatch stream prefixes.",
    )

    web_env = _environment(web)
    worker_env = _environment(worker)
    web_secrets = _secrets(web)
    worker_secrets = _secrets(worker)
    _require(REQUIRED_SHARED_ENV <= set(web_env), "Web container is missing required shared environment settings.")
    _require(REQUIRED_SHARED_SECRETS <= set(web_secrets), "Web container is missing required shared secrets.")
    for container_env in (web_env, worker_env):
        _require(
            not (WEB_ONLY_SECRETS & set(container_env)),
            "The Legacy origin header value must be a secret reference, never a literal environment value.",
        )
    _require(not (WEB_ONLY_SECRETS & set(worker_secrets)), "The worker must not receive Web-only secrets.")

    if rendered:
        _require(worker_env == web_env, "Rendered worker environment must exactly match Web.")
        _require(
            worker_secrets == {name: value for name, value in web_secrets.items() if name not in WEB_ONLY_SECRETS},
            "Rendered worker secret references must exactly match Web, minus Web-only secrets.",
        )
        _require(
            web_env["DJANGO_SETTINGS_MODULE"] == "config.settings.production",
            "Rendered containers must use production Django settings.",
        )
        if web_env["AMPLIFY_APP_ID"].strip():
            _require(
                bool(web_env["AMPLIFY_BACKEND_PROXY_URL"].strip()),
                "AMPLIFY_BACKEND_PROXY_URL is required when Amplify reconciliation is configured.",
            )
        _require(
            bool(AMPLIFY_CONFIG_REVISION_RE.fullmatch(web_env["AMPLIFY_CONFIG_REVISION"])),
            "AMPLIFY_CONFIG_REVISION must use the positive numeric '<run_id>.<run_attempt>' format.",
        )
        _require(not _contains_placeholder(taskdef), "Rendered task definition still contains a template placeholder.")
        _require(
            all(value.startswith(SECRET_ARN_PREFIXES) for value in web_secrets.values()),
            "Rendered secret valueFrom entries must be Secrets Manager or SSM ARNs.",
        )
        _validate_legacy_view(web_env, web_secrets)
    else:
        _require(
            web_env["AMPLIFY_CONFIG_REVISION"] == "__AMPLIFY_CONFIG_REVISION__",
            "Template AMPLIFY_CONFIG_REVISION must retain its deployment placeholder.",
        )
        _require(not worker_env, "Template worker environment is populated by the renderer and must start empty.")
        _require(not worker_secrets, "Template worker secrets are populated by the renderer and must start empty.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_definition", type=Path)
    parser.add_argument("--rendered", action="store_true")
    args = parser.parse_args()
    with args.task_definition.open(encoding="utf-8") as handle:
        taskdef = json.load(handle)
    try:
        validate_task_definition(taskdef, rendered=args.rendered)
    except TaskDefinitionValidationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
