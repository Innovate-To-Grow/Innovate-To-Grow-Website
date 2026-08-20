"""Bounded HTTP probes for the fixed public I2G endpoints."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .constants import HttpProbeSpec
from .types import CheckResult

MAX_RESPONSE_BYTES = 64 * 1024
DEFAULT_TIMEOUT_SECONDS = 4.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _default_transport(url: str, timeout: float) -> tuple[int, bytes, str]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json,text/html", "User-Agent": "I2G-Status-Monitor/1.0"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        return int(response.status), payload, response.headers.get("Content-Type", "")


def run_http_probe(
    spec: HttpProbeSpec,
    *,
    transport: Callable[[str, float], tuple[int, bytes, str]] = _default_transport,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    attempts: int = 2,
) -> CheckResult:
    """Execute a fixed probe and return only bounded, sanitized diagnostics."""

    started = time.monotonic()
    last_code = "HTTP_UNAVAILABLE"
    for _attempt in range(max(1, attempts)):
        try:
            status, body, content_type = transport(spec.url, timeout)
            latency = max(0, round((time.monotonic() - started) * 1000))
            if status != 200:
                last_code = f"HTTP_{status}"
                continue
            if spec.kind == "html":
                text = body.decode("utf-8", errors="ignore").lower()
                is_html = "html" in content_type.lower() and ("<html" in text or "<!doctype html" in text)
                marker_found = bool(spec.marker) and spec.marker.lower() in text
                if not is_html or not marker_found:
                    return CheckResult(spec.check_id, "http", "unhealthy", "HTML_MARKER_MISSING", latency)
                return CheckResult(spec.check_id, "http", "healthy", "HTTP_OK", latency)
            return _health_result(spec.check_id, body, content_type, latency)
        except urllib.error.HTTPError as exc:
            last_code = f"HTTP_{exc.code}"
        except urllib.error.URLError:
            last_code = "HTTP_UNAVAILABLE"
        except TimeoutError:
            last_code = "HTTP_TIMEOUT"
        except (ValueError, json.JSONDecodeError) as exc:
            last_code = "RESPONSE_TOO_LARGE" if str(exc) == "response_too_large" else "INVALID_RESPONSE"
        except Exception:  # The raw network exception must never enter persisted/public data.
            last_code = "HTTP_PROBE_ERROR"
    latency = max(0, round((time.monotonic() - started) * 1000))
    return CheckResult(spec.check_id, "http", "unhealthy", last_code, latency)


def _health_result(check_id: str, body: bytes, content_type: str, latency: int) -> CheckResult:
    if "json" not in content_type.lower() and not body.lstrip().startswith((b"{", b"[")):
        return CheckResult(check_id, "http", "unhealthy", "HEALTH_NOT_JSON", latency)
    try:
        payload: Any = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return CheckResult(check_id, "http", "unhealthy", "INVALID_HEALTH_JSON", latency)
    if not isinstance(payload, dict):
        return CheckResult(check_id, "http", "unhealthy", "INVALID_HEALTH_SHAPE", latency)

    status = str(payload.get("status", "")).strip().lower()
    database = str(payload.get("database", "")).strip().lower()
    maintenance = payload.get("maintenance") is True or status == "maintenance"
    if maintenance:
        return CheckResult(check_id, "http", "maintenance", "MAINTENANCE_ACTIVE", latency)
    if status not in {"ok", "healthy", "up", "operational"}:
        return CheckResult(check_id, "http", "unhealthy", "HEALTH_NOT_OK", latency)
    if database and database not in {"ok", "healthy", "available"}:
        return CheckResult(check_id, "http", "unhealthy", "DEPENDENCY_NOT_READY", latency)
    return CheckResult(check_id, "http", "healthy", "HEALTH_OK", latency)
