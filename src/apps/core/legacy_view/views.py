"""CloudFront-gated, viewer-authorized, read-only Legacy proxy views."""

from __future__ import annotations

import logging
import time
from http import HTTPStatus

from django.core.exceptions import ImproperlyConfigured
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseGone,
    HttpResponseNotAllowed,
    StreamingHttpResponse,
)
from django.views.decorators.csrf import csrf_exempt

from . import auth as legacy_auth
from .config import LegacyGatewayConfig, gateway_request_is_trusted, get_gateway_config
from .policies import InvalidLegacyPath, PathDecision, canonicalize_legacy_path, classify_legacy_path
from .rewriting import InvalidLegacyURL, rewrite_legacy_html, rewrite_location
from .transport import LegacyOriginHandle, LegacyOriginUnavailable, open_legacy_origin

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 5 * 1024 * 1024

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


def _plain_error(message: str, status: int) -> HttpResponse:
    return _apply_gateway_headers(HttpResponse(message, status=status, content_type="text/plain; charset=utf-8"))


def _log_response(
    request: HttpRequest,
    response: HttpResponse,
    started: float,
    outcome: str,
    *,
    canonical_path: str = "-",
    user=None,
) -> HttpResponse:
    logger.info(
        "legacy_view_request status=%s method=%s outcome=%s path=%s user_id=%s duration_ms=%s",
        response.status_code,
        request.method,
        outcome,
        canonical_path,
        getattr(user, "pk", None),
        round((time.monotonic() - started) * 1000),
    )
    return response


def _origin_content_type(handle: LegacyOriginHandle) -> str:
    return handle.response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip().lower()


def _render_head_or_empty(
    canonical_path: str,
    handle: LegacyOriginHandle,
    config: LegacyGatewayConfig,
) -> HttpResponse:
    response = HttpResponse(status=handle.response.status)
    try:
        html_response = _origin_content_type(handle) in {"text/html", "application/xhtml+xml"}
        _copy_origin_headers(response, handle, canonical_path, config, transformed_html=html_response)
        if html_response:
            # GET changes the representation, so the origin's length and range
            # metadata cannot describe a HEAD response from the viewer.
            response["Content-Type"] = "text/html; charset=utf-8"
    finally:
        handle.close()
    return _apply_gateway_headers(response)


def _render_redirect(
    canonical_path: str,
    handle: LegacyOriginHandle,
    config: LegacyGatewayConfig,
) -> HttpResponse:
    response = HttpResponse(status=handle.response.status)
    try:
        _copy_origin_headers(response, handle, canonical_path, config, include_content_length=False)
    finally:
        handle.close()
    return _apply_gateway_headers(response)


def _render_html(
    canonical_path: str,
    handle: LegacyOriginHandle,
    config: LegacyGatewayConfig,
) -> HttpResponse:
    if handle.response.status == HTTPStatus.PARTIAL_CONTENT:
        handle.close()
        raise LegacyOriginUnavailable("Partial Legacy HTML cannot be safely rewritten.")
    encoding = handle.response.headers.get("Content-Encoding", "").strip().lower()
    content_length = handle.response.headers.get("Content-Length", "").strip()
    if encoding not in {"", "identity"}:
        handle.close()
        raise LegacyOriginUnavailable("Encoded Legacy HTML cannot be safely rewritten.")
    if content_length.isdigit() and int(content_length) > MAX_HTML_BYTES:
        handle.close()
        raise LegacyOriginUnavailable("Legacy HTML response exceeded the size limit.")

    try:
        raw_content = handle.read_limited(MAX_HTML_BYTES)
    finally:
        handle.close()
    content_type = handle.response.headers.get("Content-Type", "text/html")
    charset = "utf-8"
    if "charset=" in content_type.lower():
        candidate = content_type.lower().rsplit("charset=", 1)[1].split(";", 1)[0].strip(" \"'")
        try:
            "".encode(candidate)
            charset = candidate
        except LookupError:
            charset = "utf-8"
    decoded = raw_content.decode(charset, errors="replace")

    rewritten = rewrite_legacy_html(
        decoded,
        canonical_path,
        config.origin.hostname or "",
        config.viewer_base_url,
    ).encode("utf-8")
    response = HttpResponse(rewritten, status=handle.response.status, content_type="text/html; charset=utf-8")
    _copy_origin_headers(response, handle, canonical_path, config, transformed_html=True)
    response["Content-Type"] = "text/html; charset=utf-8"
    response["Content-Length"] = str(len(rewritten))
    return _apply_gateway_headers(response)


def _render_stream(
    canonical_path: str,
    handle: LegacyOriginHandle,
    config: LegacyGatewayConfig,
) -> StreamingHttpResponse:
    # Pull one bounded chunk before committing response headers. Connection and
    # immediate read failures can then become the promised generic 502 while
    # the remainder of successful assets still streams without full buffering.
    try:
        first_chunk = handle.read_chunk()
    except LegacyOriginUnavailable:
        handle.close()
        raise
    if not first_chunk:
        handle.close()

    class LoggedOriginStream:
        def __iter__(self):
            try:
                if first_chunk:
                    yield first_chunk
                    yield from handle.iter_chunks()
            except LegacyOriginUnavailable:
                # Headers may already be on the wire, so the only safe action is
                # to terminate this representation and log the truncated stream.
                logger.warning("legacy_view_stream_failed path=%s", canonical_path, exc_info=True)

        def close(self):
            # Django calls resource closers if the client disconnects before
            # iteration starts; a generator-only finally block cannot cover that.
            handle.close()

    response = StreamingHttpResponse(LoggedOriginStream(), status=handle.response.status)
    try:
        _copy_origin_headers(response, handle, canonical_path, config)
    except InvalidLegacyURL:
        handle.close()
        raise
    return _apply_gateway_headers(response)


def legacy_proxy_view(request: HttpRequest, legacy_path: str = "") -> HttpResponse:
    started = time.monotonic()
    if not gateway_request_is_trusted(request):
        response = _plain_error("Not found.", HTTPStatus.NOT_FOUND)
        return _log_response(request, response, started, "origin_header_denied")
    request._i2g_legacy_origin_verified = True  # type: ignore[attr-defined]

    try:
        canonical_path = canonicalize_legacy_path(legacy_path)
    except InvalidLegacyPath:
        response = _plain_error("Not found.", HTTPStatus.NOT_FOUND)
        return _log_response(request, response, started, "invalid_path")

    decision = classify_legacy_path(canonical_path)
    if decision is PathDecision.BLOCK:
        response = _apply_gateway_headers(HttpResponseGone("This retired Legacy operation is no longer available."))
        return _log_response(request, response, started, "blocked_path")
    if decision is not PathDecision.ALLOW:
        response = _plain_error("Not found.", HTTPStatus.NOT_FOUND)
        return _log_response(request, response, started, "unknown_path")
    if request.method not in {"GET", "HEAD"}:
        response = _apply_gateway_headers(HttpResponseNotAllowed(["GET", "HEAD"]))
        return _log_response(request, response, started, "method_denied", canonical_path=canonical_path)

    try:
        user = legacy_auth.require_legacy_viewer(request)
    except Exception as exc:
        if not legacy_auth.is_legacy_viewer_access_denied(exc):
            raise
        response = _apply_gateway_headers(HttpResponseForbidden("Legacy viewer authorization is required."))
        response = legacy_auth.clear_legacy_viewer_cookie(response)
        return _log_response(request, response, started, "viewer_denied", canonical_path=canonical_path)

    try:
        config = get_gateway_config()
        handle = open_legacy_origin(request, canonical_path, config)
        if not 200 <= handle.response.status < 500:
            handle.close()
            raise LegacyOriginUnavailable("Legacy origin returned an invalid or server-error status.")
        if request.method == "HEAD" or handle.response.status in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED}:
            response = _render_head_or_empty(canonical_path, handle, config)
        elif 300 <= handle.response.status < 400:
            response = _render_redirect(canonical_path, handle, config)
        elif _origin_content_type(handle) in {"text/html", "application/xhtml+xml"}:
            response = _render_html(canonical_path, handle, config)
        else:
            response = _render_stream(canonical_path, handle, config)
    except (ImproperlyConfigured, InvalidLegacyURL, LegacyOriginUnavailable):
        logger.exception("legacy_view_origin_failed outcome=origin_failure path=%s", canonical_path)
        response = _plain_error("Legacy content is temporarily unavailable.", HTTPStatus.BAD_GATEWAY)
        return _log_response(
            request,
            response,
            started,
            "origin_failure",
            canonical_path=canonical_path,
            user=user,
        )
    return _log_response(
        request,
        response,
        started,
        "success",
        canonical_path=canonical_path,
        user=user,
    )


@csrf_exempt
def legacy_access_exchange_gateway(request: HttpRequest) -> HttpResponse:
    """Expose the one authorized POST endpoint after CloudFront verification."""

    started = time.monotonic()
    if not gateway_request_is_trusted(request):
        response = _plain_error("Not found.", HTTPStatus.NOT_FOUND)
        logger.info(
            "legacy_view_exchange status=%s method=%s outcome=origin_header_denied duration_ms=%s",
            response.status_code,
            request.method,
            round((time.monotonic() - started) * 1000),
        )
        return response
    request._i2g_legacy_origin_verified = True  # type: ignore[attr-defined]
    if request.method != "POST":
        response = _apply_gateway_headers(HttpResponseNotAllowed(["POST"]))
        logger.info(
            "legacy_view_exchange status=%s method=%s outcome=method_denied duration_ms=%s",
            response.status_code,
            request.method,
            round((time.monotonic() - started) * 1000),
        )
        return response

    from apps.core.views.legacy_access import legacy_access_exchange_view

    response = _apply_gateway_headers(legacy_access_exchange_view(request))
    logger.info(
        "legacy_view_exchange status=%s method=%s outcome=dispatched duration_ms=%s",
        response.status_code,
        request.method,
        round((time.monotonic() - started) * 1000),
    )
    return response
