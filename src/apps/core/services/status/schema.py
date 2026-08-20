"""Validation limits for the internal status API response."""

from __future__ import annotations

import math
from typing import Any

from .errors import StatusFetchError

EXPECTED_SCHEMA_VERSION = 1
MAX_COLLECTION_ITEMS = {
    "errors": 50,
    "resources": 250,
    "services": 50,
    "probes": 100,
    "alarms": 200,
}
MAX_STRING_LENGTH = 4096
MAX_JSON_DEPTH = 12


def validate_status_payload(payload: dict[str, Any]) -> None:
    """Apply tight structural and size checks before caching upstream data."""

    required_types = {
        "schemaVersion": int,
        "generatedAt": str,
        "partial": bool,
        "errors": list,
        "stack": dict,
        "services": list,
        "probes": list,
        "alarms": list,
    }
    if type(payload.get("schemaVersion")) is not int or payload["schemaVersion"] != EXPECTED_SCHEMA_VERSION:
        raise StatusFetchError("invalid_response")
    if any(key not in payload or not isinstance(payload[key], expected) for key, expected in required_types.items()):
        raise StatusFetchError("invalid_response")
    if not payload["generatedAt"].strip():
        raise StatusFetchError("invalid_response")

    for key in ("errors", "services", "probes", "alarms"):
        if len(payload[key]) > MAX_COLLECTION_ITEMS[key] or any(not isinstance(item, dict) for item in payload[key]):
            raise StatusFetchError("invalid_response")
    resources = payload["stack"].get("resources", [])
    if not isinstance(resources, list) or len(resources) > MAX_COLLECTION_ITEMS["resources"]:
        raise StatusFetchError("invalid_response")
    if any(not isinstance(item, dict) for item in resources):
        raise StatusFetchError("invalid_response")

    _validate_json_limits(payload)


def _validate_json_limits(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise StatusFetchError("invalid_response")
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise StatusFetchError("invalid_response")
        return
    if isinstance(value, dict):
        if len(value) > 100:
            raise StatusFetchError("invalid_response")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise StatusFetchError("invalid_response")
            _validate_json_limits(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 500:
            raise StatusFetchError("invalid_response")
        for item in value:
            _validate_json_limits(item, depth=depth + 1)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise StatusFetchError("invalid_response")
    if value is not None and not isinstance(value, (bool, int, float)):
        raise StatusFetchError("invalid_response")
