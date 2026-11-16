"""The gateway response's headers: which origin headers are copied, and the Legacy CSP and gateway headers added."""

from __future__ import annotations

from django.http import HttpResponse

from ..origin.config import LegacyGatewayConfig
from ..origin.transport import LegacyOriginHandle
from .link_rewriting import rewrite_location

_COPIED_RESPONSE_HEADERS = (
    "Accept-Ranges",
    "Content-Disposition",
    "Content-Encoding",
    "Content-Length",
    "Content-Range",
    "Content-Type",
    "ETag",
    "Expires",
    "Last-Modified",
)


_LEGACY_CSP = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://ajax.googleapis.com https://cdnjs.cloudflare.com "
        "https://code.jquery.com https://cdn.datatables.net",
        "script-src-attr 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.datatables.net "
        "https://css.gg https://fonts.googleapis.com",
        "img-src 'self' data: blob: https:",
        "font-src 'self' data: https://cdnjs.cloudflare.com https://fonts.gstatic.com",
        "connect-src 'self' https://sheets.googleapis.com",
        "media-src 'self' https:",
        "frame-src https:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)


def _safe_response_header(value: str) -> str:
    return value if value and len(value) <= 4096 and "\r" not in value and "\n" not in value else ""


def _apply_gateway_headers(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Content-Security-Policy"] = _LEGACY_CSP
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    response["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(), payment=()"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    return response


def _copy_origin_headers(
    response: HttpResponse,
    handle: LegacyOriginHandle,
    canonical_path: str,
    config: LegacyGatewayConfig,
    *,
    transformed_html: bool = False,
    include_content_length: bool = True,
) -> None:
    for name in _COPIED_RESPONSE_HEADERS:
        if transformed_html and name in {
            "Accept-Ranges",
            "Content-Encoding",
            "Content-Length",
            "Content-Range",
            "ETag",
        }:
            continue
        if not include_content_length and name == "Content-Length":
            continue
        value = _safe_response_header(handle.response.headers.get(name, ""))
        if value:
            response[name] = value

    location = _safe_response_header(handle.response.headers.get("Location", ""))
    if location:
        response["Location"] = rewrite_location(
            location,
            canonical_path,
            config.origin.hostname or "",
            config.viewer_base_url,
        )
