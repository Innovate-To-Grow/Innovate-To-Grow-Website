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
)
from django.views.decorators.csrf import csrf_exempt

from . import auth as legacy_auth
from .config import gateway_request_is_trusted, get_gateway_config
from .policies import InvalidLegacyPath, PathDecision, canonicalize_legacy_path, classify_legacy_path

# ``MAX_HTML_BYTES`` and ``_LEGACY_CSP`` are re-exported: callers and tests import them from here.
from .responses import (
    _LEGACY_CSP as _LEGACY_CSP,
)
from .responses import (
    MAX_HTML_BYTES as MAX_HTML_BYTES,
)
from .responses import (
    _apply_gateway_headers,
    _origin_content_type,
    _plain_error,
    _render_head_or_empty,
    _render_html,
    _render_redirect,
    _render_stream,
)
from .rewriting import InvalidLegacyURL
from .transport import LegacyOriginUnavailable, open_legacy_origin

logger = logging.getLogger(__name__)


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


def legacy_proxy_view(request: HttpRequest, legacy_path: str = "") -> HttpResponse:
    started = time.monotonic()
    if not gateway_request_is_trusted(request):
        response = _plain_error("Not found.", HTTPStatus.NOT_FOUND)
        return _log_response(request, response, started, "origin_header_denied")
    request._i2g_legacy_origin_verified = True  # type: ignore[attr-defined]

    canonical_path, refusal = _allowed_path(request, legacy_path)
    if refusal is not None:
        response, outcome = refusal
        extra = {"canonical_path": canonical_path} if outcome == "method_denied" else {}
        return _log_response(request, response, started, outcome, **extra)

    try:
        user = legacy_auth.require_legacy_viewer(request)
    except Exception as exc:
        if not legacy_auth.is_legacy_viewer_access_denied(exc):
            raise
        response = _apply_gateway_headers(HttpResponseForbidden("Legacy viewer authorization is required."))
        response = legacy_auth.clear_legacy_viewer_cookie(response)
        return _log_response(request, response, started, "viewer_denied", canonical_path=canonical_path)

    try:
        response = _proxy_origin(request, canonical_path)
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


def _allowed_path(request: HttpRequest, legacy_path: str):
    """``(canonical_path, None)`` for a readable path, else ``(path, (response, outcome))`` refusing it."""
    try:
        canonical_path = canonicalize_legacy_path(legacy_path)
    except InvalidLegacyPath:
        return "", (_plain_error("Not found.", HTTPStatus.NOT_FOUND), "invalid_path")

    decision = classify_legacy_path(canonical_path)
    if decision is PathDecision.BLOCK:
        gone = HttpResponseGone("This retired Legacy operation is no longer available.")
        return canonical_path, (_apply_gateway_headers(gone), "blocked_path")
    if decision is not PathDecision.ALLOW:
        return canonical_path, (_plain_error("Not found.", HTTPStatus.NOT_FOUND), "unknown_path")
    if request.method not in {"GET", "HEAD"}:
        return canonical_path, (_apply_gateway_headers(HttpResponseNotAllowed(["GET", "HEAD"])), "method_denied")
    return canonical_path, None


def _proxy_origin(request: HttpRequest, canonical_path: str) -> HttpResponse:
    config = get_gateway_config()
    handle = open_legacy_origin(request, canonical_path, config)
    if not 200 <= handle.response.status < 500:
        handle.close()
        raise LegacyOriginUnavailable("Legacy origin returned an invalid or server-error status.")
    if request.method == "HEAD" or handle.response.status in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED}:
        return _render_head_or_empty(canonical_path, handle, config)
    if 300 <= handle.response.status < 400:
        return _render_redirect(canonical_path, handle, config)
    if _origin_content_type(handle) in {"text/html", "application/xhtml+xml"}:
        return _render_html(canonical_path, handle, config)
    return _render_stream(canonical_path, handle, config)


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
