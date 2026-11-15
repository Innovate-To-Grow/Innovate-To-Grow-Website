#!/usr/bin/env python3
"""Validate the production/demo backend ECS task topology before rollout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .task_definition_legacy_view import _validate_legacy_view
from .task_definition_rules import (
    AMPLIFY_CONFIG_REVISION_RE,
    POSITIVE_INT_RE,
    REQUIRED_SHARED_ENV,
    REQUIRED_SHARED_SECRETS,
    SECRET_ARN_PREFIXES,
    WEB_CONTAINER,
    WEB_ONLY_SECRETS,
    WORKER_COMMAND,
    WORKER_CONTAINER,
    WORKER_ENTRYPOINT,
    TaskDefinitionValidationError,
    _contains_placeholder,
    _environment,
    _require,
    _secrets,
)
from .task_definition_rules import PLACEHOLDER_RE as PLACEHOLDER_RE  # the ECS topology tests read it from here


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
        "Worker must wait for Web health before processing background jobs.",
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
            web_env["DJANGO_SETTINGS_MODULE"] == "config.settings.environments.production",
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
        _require(
            bool(POSITIVE_INT_RE.fullmatch(web_env["NUM_PROXIES"])),
            "NUM_PROXIES must be a positive integer (trusted proxy hops in front of uvicorn; the ALB is one).",
        )
        _require(not _contains_placeholder(taskdef), "Rendered task definition still contains a template placeholder.")
        _require(
            all(value.startswith(SECRET_ARN_PREFIXES) for value in web_secrets.values()),
            "Rendered secret valueFrom entries must be Secrets Manager or SSM ARNs.",
        )
        _validate_legacy_view(web_env, web_secrets)
    else:
        _require(
            web_env["NUM_PROXIES"] == "__NUM_PROXIES__",
            "Template NUM_PROXIES must retain its deployment placeholder.",
        )
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
