#!/usr/bin/env python3
"""Render immutable ECS task definitions from checked-in templates.

Only deployment-time references are read from the environment. Secret values
are never accepted here: ECS receives Secrets Manager or SSM ARNs through each
container's ``secrets`` entries.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EMPTY_SENTINELS = {"__EMPTY__", "__UNSET__", "null", "None"}
PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def env_value(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    if value is None or value in EMPTY_SENTINELS:
        return ""
    return value


def enabled(name: str) -> bool:
    return env_value(name).strip().lower() in TRUE_VALUES


def normalized_boolean(name: str, *, default: bool) -> str:
    value = env_value(name, "true" if default else "false").strip().lower()
    if value in TRUE_VALUES:
        return "true"
    if value in FALSE_VALUES:
        return "false"
    raise SystemExit(f"{name} must be a boolean value.")


def worker_deploy_enabled() -> bool:
    """Keep the legacy producer flag as the fallback worker rollout switch."""
    configured = env_value("BACKGROUND_WORKER_ENABLED").strip()
    if configured:
        return configured.lower() in TRUE_VALUES
    return enabled("BACKGROUND_JOBS_ENABLED")


def origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value.rstrip("/")


def required_runtime_environment() -> dict[str, str]:
    """Resolve settings required when importing production Django settings."""
    frontend_url = env_value("FRONTEND_URL").strip()
    backend_url = env_value("BACKEND_URL").strip()
    api_base_url = env_value("API_BASE_URL").strip()
    frontend_origin = origin(frontend_url)
    backend_origin = origin(backend_url)
    api_origin = origin(api_base_url)

    csrf_origins = env_value("CSRF_TRUSTED_ORIGINS").strip()
    if not csrf_origins:
        csrf_origins = ",".join(item for item in (frontend_origin, backend_origin, api_origin) if item)
    cors_origins = env_value("CORS_ALLOWED_ORIGINS").strip() or frontend_origin

    configured_hosts = env_value("DJANGO_ALLOWED_HOSTS").strip()
    hosts = [item.strip() for item in configured_hosts.split(",") if item.strip()]
    for url in (api_base_url, frontend_url, backend_url):
        parsed = urlparse(url)
        if parsed.hostname:
            hosts.append(parsed.hostname)
    if not configured_hosts:
        hosts.extend([".cloudfront.net", ".elb.amazonaws.com"])

    values = {
        "DJANGO_ALLOWED_HOSTS": ",".join(dict.fromkeys(hosts)),
        "BACKEND_URL": backend_url,
        "AWS_STORAGE_BUCKET_NAME": env_value("AWS_STORAGE_BUCKET_NAME").strip(),
        "AWS_S3_REGION_NAME": env_value("AWS_S3_REGION_NAME", "us-west-2").strip(),
        "FRONTEND_URL": frontend_url,
        "CSRF_TRUSTED_ORIGINS": csrf_origins,
        "CORS_ALLOWED_ORIGINS": cors_origins,
    }
    required_names = (
        "DJANGO_ALLOWED_HOSTS",
        "BACKEND_URL",
        "FRONTEND_URL",
        "AWS_STORAGE_BUCKET_NAME",
        "AWS_S3_REGION_NAME",
    )
    missing = [name for name in required_names if not values[name]]
    if missing:
        raise SystemExit(f"Required production environment values are empty: {', '.join(missing)}.")
    return values


def require_iam_role(name: str, value: str) -> str:
    value = value.strip()
    if not value.startswith("arn:aws:iam::") or ":role/" not in value:
        raise SystemExit(f"{name} must be a complete AWS IAM role ARN.")
    return value


def require_secret_ref(name: str, value: str) -> str:
    value = value.strip()
    if not value.startswith(("arn:aws:secretsmanager:", "arn:aws:ssm:")):
        raise SystemExit(f"{name} must be a Secrets Manager or SSM Parameter Store ARN.")
    return value


def set_container_environment(container: dict[str, Any], values_by_name: dict[str, str]) -> None:
    existing = {item.get("name"): item for item in container.setdefault("environment", []) if item.get("name")}
    for name, value in values_by_name.items():
        if name in existing:
            existing[name]["value"] = value
        else:
            container["environment"].append({"name": name, "value": value})


def render_secrets(
    container: dict[str, Any],
    values_by_placeholder: dict[str, str],
    required: set[str],
) -> None:
    rendered: list[dict[str, Any]] = []
    for item in container.get("secrets", []):
        placeholder = item.get("valueFrom", "")
        if placeholder not in values_by_placeholder:
            rendered.append(item)
            continue

        value = values_by_placeholder[placeholder].strip()
        if not value:
            if placeholder in required:
                raise SystemExit(f"{placeholder.strip('_')} is required for this deployment.")
            continue
        item["valueFrom"] = require_secret_ref(placeholder.strip("_"), value)
        rendered.append(item)
    container["secrets"] = rendered


def assert_no_placeholders(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        match = PLACEHOLDER_RE.search(value)
        if match:
            raise SystemExit(f"Unresolved placeholder {match.group()} at {path}.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_placeholders(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_placeholders(item, f"{path}.{key}")


def dump_json(path: Path, value: dict[str, Any]) -> None:
    assert_no_placeholders(value)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def render_web(
    template: Path,
    output: Path,
    one_off_output: Path,
    runtime_environment: dict[str, str],
) -> None:
    taskdef = json.loads(template.read_text(encoding="utf-8"))
    container = taskdef["containerDefinitions"][0]

    task_family = env_value("ECS_TASK_FAMILY", "itg-backend").strip()
    taskdef["family"] = task_family
    taskdef["executionRoleArn"] = require_iam_role("ECS_EXECUTION_ROLE_ARN", env_value("ECS_EXECUTION_ROLE_ARN"))
    taskdef["taskRoleArn"] = require_iam_role("ECS_TASK_ROLE_ARN", env_value("ECS_TASK_ROLE_ARN"))
    container["image"] = env_value("IMAGE_URI").strip()
    if not container["image"]:
        raise SystemExit("IMAGE_URI is required.")

    values_by_placeholder = {
        "__DJANGO_ALLOWED_HOSTS__": runtime_environment["DJANGO_ALLOWED_HOSTS"],
        "__DB_NAME__": env_value("DB_NAME"),
        "__DB_USER__": env_value("DB_USER"),
        "__DB_HOST__": env_value("DB_HOST"),
        "__DB_PORT__": env_value("DB_PORT", "5432"),
        "__DB_CONN_MAX_AGE__": env_value("DB_CONN_MAX_AGE", "0"),
        "__DB_CONN_HEALTH_CHECKS__": env_value("DB_CONN_HEALTH_CHECKS", "true"),
        "__WEB_CONCURRENCY__": env_value("WEB_CONCURRENCY", "2"),
        "__UVICORN_LIMIT_CONCURRENCY__": env_value("UVICORN_LIMIT_CONCURRENCY", "20"),
        "__CSRF_TRUSTED_ORIGINS__": runtime_environment["CSRF_TRUSTED_ORIGINS"],
        "__CORS_ALLOWED_ORIGINS__": runtime_environment["CORS_ALLOWED_ORIGINS"],
        "__CSP_REPORT_ONLY__": normalized_boolean(
            "CSP_REPORT_ONLY",
            default=True,
        ),
        "__FRONTEND_URL__": runtime_environment["FRONTEND_URL"],
        "__BACKEND_URL__": runtime_environment["BACKEND_URL"],
        "__AWS_STORAGE_BUCKET_NAME__": runtime_environment["AWS_STORAGE_BUCKET_NAME"],
        "__AWS_S3_REGION_NAME__": runtime_environment["AWS_S3_REGION_NAME"],
        "__DJANGO_SUPERUSER_USERNAME__": env_value("DJANGO_SUPERUSER_USERNAME"),
        "__DJANGO_SUPERUSER_EMAIL__": env_value("DJANGO_SUPERUSER_EMAIL"),
        "__DJANGO_SUPERUSER_FIRST_NAME__": env_value("DJANGO_SUPERUSER_FIRST_NAME", "Demo"),
        "__DJANGO_SUPERUSER_LAST_NAME__": env_value("DJANGO_SUPERUSER_LAST_NAME", "Admin"),
        "__ENSURE_DEFAULT_ADMIN__": ("true" if enabled("ENSURE_DEFAULT_ADMIN") else "false"),
    }
    for item in container.get("environment", []):
        placeholder = item.get("value", "")
        if placeholder in values_by_placeholder:
            item["value"] = values_by_placeholder[placeholder]

    background_enabled = enabled("BACKGROUND_JOBS_ENABLED")
    set_container_environment(
        container,
        {
            "BACKGROUND_JOBS_ENABLED": ("true" if background_enabled else "false"),
            "BACKGROUND_JOB_METRICS_NAMESPACE": env_value("BACKGROUND_JOB_METRICS_NAMESPACE", "I2G/BackgroundJobs"),
        },
    )

    db_engine = env_value("DB_ENGINE").strip()
    if db_engine:
        set_container_environment(container, {"DB_ENGINE": db_engine})

    secret_values = {
        "__DJANGO_SECRET_KEY_SECRET_ARN__": env_value("DJANGO_SECRET_KEY_SECRET_ARN"),
        "__DB_PASSWORD_SECRET_ARN__": env_value("DB_PASSWORD_SECRET_ARN"),
        "__REDIS_URL_SECRET_ARN__": env_value("REDIS_URL_SECRET_ARN"),
        "__DJANGO_SUPERUSER_PASSWORD_SECRET_ARN__": env_value("DJANGO_SUPERUSER_PASSWORD_SECRET_ARN"),
    }
    required_secrets = {
        "__DJANGO_SECRET_KEY_SECRET_ARN__",
        "__DB_PASSWORD_SECRET_ARN__",
    }
    if background_enabled:
        required_secrets.add("__REDIS_URL_SECRET_ARN__")
    if enabled("ENSURE_DEFAULT_ADMIN"):
        if not env_value("DJANGO_SUPERUSER_EMAIL").strip():
            raise SystemExit("DJANGO_SUPERUSER_EMAIL is required when ENSURE_DEFAULT_ADMIN is true.")
        required_secrets.add("__DJANGO_SUPERUSER_PASSWORD_SECRET_ARN__")
    render_secrets(container, secret_values, required_secrets)

    log_options = container.setdefault("logConfiguration", {}).setdefault("options", {})
    log_options["awslogs-group"] = env_value("ECS_LOG_GROUP", "/ecs/itg-backend")
    log_options["awslogs-region"] = env_value("AWS_REGION", "us-west-2")
    dump_json(output, taskdef)

    one_off = copy.deepcopy(taskdef)
    one_off["family"] = f"{task_family}-oneoff"
    one_off_container = one_off["containerDefinitions"][0]
    one_off_container.pop("healthCheck", None)
    one_off_container.pop("portMappings", None)
    dump_json(one_off_output, one_off)


def render_worker(template: Path, output: Path, runtime_environment: dict[str, str]) -> None:
    if not worker_deploy_enabled():
        output.unlink(missing_ok=True)
        return

    taskdef = json.loads(template.read_text(encoding="utf-8"))
    container = taskdef["containerDefinitions"][0]
    taskdef["family"] = env_value("ECS_WORKER_TASK_FAMILY").strip()
    if not taskdef["family"]:
        raise SystemExit("ECS_WORKER_TASK_FAMILY is required when background jobs are enabled.")
    taskdef["executionRoleArn"] = require_iam_role("ECS_EXECUTION_ROLE_ARN", env_value("ECS_EXECUTION_ROLE_ARN"))
    taskdef["taskRoleArn"] = require_iam_role("ECS_TASK_ROLE_ARN", env_value("ECS_TASK_ROLE_ARN"))
    container["image"] = env_value("IMAGE_URI").strip()

    values_by_placeholder = {
        "__DJANGO_ALLOWED_HOSTS__": runtime_environment["DJANGO_ALLOWED_HOSTS"],
        "__BACKEND_URL__": runtime_environment["BACKEND_URL"],
        "__FRONTEND_URL__": runtime_environment["FRONTEND_URL"],
        "__AWS_STORAGE_BUCKET_NAME__": runtime_environment["AWS_STORAGE_BUCKET_NAME"],
        "__AWS_S3_REGION_NAME__": runtime_environment["AWS_S3_REGION_NAME"],
        "__WORKER_BACKGROUND_JOBS_ENABLED__": "true",
        "__BACKGROUND_JOB_METRICS_NAMESPACE__": env_value("BACKGROUND_JOB_METRICS_NAMESPACE", "I2G/BackgroundJobs"),
        "__DB_NAME__": env_value("DB_NAME"),
        "__DB_USER__": env_value("DB_USER"),
        "__DB_HOST__": env_value("DB_HOST"),
        "__DB_PORT__": env_value("DB_PORT", "5432"),
        "__DB_CONN_MAX_AGE__": env_value("DB_CONN_MAX_AGE", "0"),
        "__DB_CONN_HEALTH_CHECKS__": env_value("DB_CONN_HEALTH_CHECKS", "true"),
    }
    for item in container.get("environment", []):
        placeholder = item.get("value", "")
        if placeholder in values_by_placeholder:
            item["value"] = values_by_placeholder[placeholder]

    render_secrets(
        container,
        {
            "__DJANGO_SECRET_KEY_SECRET_ARN__": env_value("DJANGO_SECRET_KEY_SECRET_ARN"),
            "__DB_PASSWORD_SECRET_ARN__": env_value("DB_PASSWORD_SECRET_ARN"),
            "__REDIS_URL_SECRET_ARN__": env_value("REDIS_URL_SECRET_ARN"),
        },
        {
            "__DJANGO_SECRET_KEY_SECRET_ARN__",
            "__DB_PASSWORD_SECRET_ARN__",
            "__REDIS_URL_SECRET_ARN__",
        },
    )
    log_options = container.setdefault("logConfiguration", {}).setdefault("options", {})
    log_options["awslogs-group"] = env_value("ECS_WORKER_LOG_GROUP")
    log_options["awslogs-region"] = env_value("AWS_REGION", "us-west-2")
    dump_json(output, taskdef)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-template", type=Path, required=True)
    parser.add_argument("--worker-template", type=Path, required=True)
    parser.add_argument("--web-output", type=Path, required=True)
    parser.add_argument("--one-off-output", type=Path, required=True)
    parser.add_argument("--worker-output", type=Path, required=True)
    args = parser.parse_args()

    runtime_environment = required_runtime_environment()
    render_web(args.web_template, args.web_output, args.one_off_output, runtime_environment)
    render_worker(args.worker_template, args.worker_output, runtime_environment)


if __name__ == "__main__":
    main()
