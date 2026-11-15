"""Container names, required settings and helpers shared by the backend task-definition checks."""

from __future__ import annotations

import re
from typing import Any

WEB_CONTAINER = "itg-backend"


WORKER_CONTAINER = "itg-background-worker"


WORKER_ENTRYPOINT = ["python"]


WORKER_COMMAND = [
    "manage.py",
    "run_background_worker",
    "--settings=config.settings.environments.production",
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
    "NUM_PROXIES",
}


REQUIRED_SHARED_SECRETS = {"DJANGO_SECRET_KEY", "DB_PASSWORD"}


# Secrets that authenticate inbound HTTP and must never reach the worker.
WEB_ONLY_SECRETS = {"LEGACY_ORIGIN_HEADER_VALUE"}


SECRET_ARN_PREFIXES = ("arn:aws:secretsmanager:", "arn:aws:ssm:")


TRUE_VALUES = {"1", "true", "yes", "on"}


PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")


AMPLIFY_CONFIG_REVISION_RE = re.compile(r"^[1-9][0-9]*\.[1-9][0-9]*$")


POSITIVE_INT_RE = re.compile(r"^[1-9][0-9]*$")


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
