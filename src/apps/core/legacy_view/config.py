"""Runtime configuration and CloudFront origin authentication."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.crypto import constant_time_compare

EXPECTED_ORIGIN_HOST = "172.31.69.63"
EXPECTED_ORIGIN_PORT = 8080

_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_CLOUDFRONT_HOST_PATTERN = re.compile(r"^d[a-z0-9]+\.cloudfront\.net$")
_FORBIDDEN_SHARED_HEADERS = {
    "authorization",
    "cookie",
    "host",
    "proxy-authorization",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
}


@dataclass(frozen=True)
class LegacyGatewayConfig:
    origin: SplitResult
    viewer_base_url: str
    origin_header_name: str
    origin_header_value: str
    connect_timeout_seconds: float
    read_timeout_seconds: float


def legacy_view_enabled() -> bool:
    """Return the fail-closed feature flag value."""

    value = getattr(settings, "LEGACY_VIEW_ENABLED", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _required_setting(name: str) -> str:
    value = str(getattr(settings, name, "") or "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set when LEGACY_VIEW_ENABLED is true.")
    return value


def _timeout_setting(name: str, default: float, maximum: float) -> float:
    raw_value = getattr(settings, name, default)
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"{name} must be a number.") from exc
    if not 0.1 <= value <= maximum:
        raise ImproperlyConfigured(f"{name} must be between 0.1 and {maximum} seconds.")
    return value


def _parse_origin(value: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured("LEGACY_ORIGIN_URL is invalid.") from exc

    if (
        parsed.scheme != "http"
        or parsed.hostname != EXPECTED_ORIGIN_HOST
        or port != EXPECTED_ORIGIN_PORT
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ImproperlyConfigured(
            f"LEGACY_ORIGIN_URL must be exactly http://{EXPECTED_ORIGIN_HOST}:{EXPECTED_ORIGIN_PORT}."
        )
    return parsed


def _parse_viewer_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured("LEGACY_VIEWER_URL is invalid.") from exc
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not _CLOUDFRONT_HOST_PATTERN.fullmatch(hostname)
        or port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ImproperlyConfigured("LEGACY_VIEWER_URL must be an HTTPS *.cloudfront.net origin without a path.")
    return f"https://{hostname}"


def _shared_header_settings() -> tuple[str, str]:
    name = str(getattr(settings, "LEGACY_ORIGIN_HEADER_NAME", "") or "").strip()
    value = str(getattr(settings, "LEGACY_ORIGIN_HEADER_VALUE", "") or "").strip()
    if (
        not _HEADER_NAME_PATTERN.fullmatch(name)
        or name.lower() in _FORBIDDEN_SHARED_HEADERS
        or len(value) < 32
        or len(value) > 512
    ):
        return "", ""
    return name, value


def gateway_request_is_trusted(request: HttpRequest) -> bool:
    """Authenticate CloudFront without ever echoing the shared secret."""

    if not legacy_view_enabled():
        return False
    header_name, expected = _shared_header_settings()
    if not header_name:
        return False
    supplied = request.headers.get(header_name, "")
    return bool(supplied) and constant_time_compare(supplied, expected)


def get_gateway_config() -> LegacyGatewayConfig:
    """Validate settings needed after a request has passed the origin guard."""

    if not legacy_view_enabled():
        raise ImproperlyConfigured("The Legacy viewer is disabled.")

    header_name, header_value = _shared_header_settings()
    if not header_name:
        raise ImproperlyConfigured(
            "LEGACY_ORIGIN_HEADER_NAME must be a safe HTTP header name and "
            "LEGACY_ORIGIN_HEADER_VALUE must contain at least 32 characters."
        )

    return LegacyGatewayConfig(
        origin=_parse_origin(_required_setting("LEGACY_ORIGIN_URL")),
        viewer_base_url=_parse_viewer_url(_required_setting("LEGACY_VIEWER_URL")),
        origin_header_name=header_name,
        origin_header_value=header_value,
        connect_timeout_seconds=_timeout_setting("LEGACY_CONNECT_TIMEOUT_SECONDS", 2.0, 30.0),
        read_timeout_seconds=_timeout_setting("LEGACY_READ_TIMEOUT_SECONDS", 10.0, 120.0),
    )
