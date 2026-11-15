"""The legacy-view settings check of the backend task definition (validate_backend_task_definition)."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from .task_definition_rules import TRUE_VALUES, _require

HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


CLOUDFRONT_HOST_RE = re.compile(r"^d[a-z0-9]+\.cloudfront\.net$")


LEGACY_TIMEOUT_LIMITS = {"LEGACY_CONNECT_TIMEOUT_SECONDS": 30.0, "LEGACY_READ_TIMEOUT_SECONDS": 120.0}


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
