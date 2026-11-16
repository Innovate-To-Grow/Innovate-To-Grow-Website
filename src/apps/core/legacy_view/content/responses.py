"""Turning a Legacy origin response into the gateway's response: HTML rewriting, streaming (headers and CSP: ``headers``)."""

from __future__ import annotations

import logging
from http import HTTPStatus

from django.http import HttpResponse, StreamingHttpResponse

from ..origin.config import LegacyGatewayConfig
from ..origin.transport import LegacyOriginHandle, LegacyOriginUnavailable
from .headers import _apply_gateway_headers, _copy_origin_headers
from .html_rewriting import rewrite_legacy_html
from .link_rewriting import InvalidLegacyURL

# These helpers used to live in ``views``; keep that logger name.
logger = logging.getLogger("apps.core.legacy_view.views")

MAX_HTML_BYTES = 5 * 1024 * 1024


def _plain_error(message: str, status: int) -> HttpResponse:
    return _apply_gateway_headers(HttpResponse(message, status=status, content_type="text/plain; charset=utf-8"))


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
