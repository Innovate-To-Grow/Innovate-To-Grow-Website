"""Small fixed-origin HTTP transport with no redirects or ambient credentials."""

from __future__ import annotations

import http.client
import re
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import quote

from django.http import HttpRequest

from .config import LegacyGatewayConfig
from .policies import filter_query_string

_RANGE_PATTERN = re.compile(r"^bytes=(?:\d+-\d*|\d*-\d+)(?:,\s*(?:\d+-\d*|\d*-\d+)){0,4}$")

_FORWARDED_REQUEST_HEADERS = {
    "Accept": ("Accept", 1024),
    "Accept-Language": ("Accept-Language", 512),
    "If-Modified-Since": ("If-Modified-Since", 128),
    "If-None-Match": ("If-None-Match", 512),
    "If-Range": ("If-Range", 512),
}


class LegacyOriginUnavailable(Exception):
    """The private origin could not safely complete the current operation."""


@dataclass
class LegacyOriginHandle:
    connection: http.client.HTTPConnection
    response: http.client.HTTPResponse
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.response.close()
        finally:
            self.connection.close()

    def read_limited(self, limit: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            while True:
                chunk = self.response.read(min(64 * 1024, limit + 1 - total))
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
                total += len(chunk)
                if total > limit:
                    raise LegacyOriginUnavailable("Legacy HTML response exceeded the size limit.")
        except (http.client.HTTPException, OSError) as exc:
            raise LegacyOriginUnavailable("Legacy origin response failed.") from exc

    def read_chunk(self, chunk_size: int = 64 * 1024) -> bytes:
        try:
            return self.response.read(chunk_size)
        except (http.client.HTTPException, OSError) as exc:
            raise LegacyOriginUnavailable("Legacy origin response failed.") from exc

    def iter_chunks(self, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        try:
            while chunk := self.response.read(chunk_size):
                yield chunk
        except (http.client.HTTPException, OSError) as exc:
            raise LegacyOriginUnavailable("Legacy origin stream failed.") from exc
        finally:
            self.close()


def _safe_header_value(value: str, maximum_length: int) -> str:
    if not value or len(value) > maximum_length or "\r" in value or "\n" in value:
        return ""
    return value


def build_origin_headers(request: HttpRequest) -> dict[str, str]:
    """Copy only representation/range headers, never cookies or credentials."""

    headers = {"Accept-Encoding": "identity", "User-Agent": "I2G-Legacy-Read-Only-Gateway/1.0"}
    for incoming_name, (outgoing_name, maximum_length) in _FORWARDED_REQUEST_HEADERS.items():
        value = _safe_header_value(request.headers.get(incoming_name, ""), maximum_length)
        if value:
            headers[outgoing_name] = value

    range_value = _safe_header_value(request.headers.get("Range", ""), 256)
    if range_value and _RANGE_PATTERN.fullmatch(range_value):
        headers["Range"] = range_value
    return headers


def build_origin_target(canonical_path: str, raw_query_string: str) -> str:
    encoded_path = quote(canonical_path, safe="/-._~")
    filtered_query = filter_query_string(raw_query_string)
    return f"{encoded_path}?{filtered_query}" if filtered_query else encoded_path


def open_legacy_origin(
    request: HttpRequest,
    canonical_path: str,
    config: LegacyGatewayConfig,
) -> LegacyOriginHandle:
    """Open one request to the hard-pinned private IP without following redirects."""

    connection = http.client.HTTPConnection(
        config.origin.hostname,
        config.origin.port,
        timeout=config.connect_timeout_seconds,
    )
    try:
        connection.connect()
        if connection.sock is not None:
            connection.sock.settimeout(config.read_timeout_seconds)
        connection.request(
            request.method,
            build_origin_target(canonical_path, request.META.get("QUERY_STRING", "")),
            body=None,
            headers=build_origin_headers(request),
        )
        response = connection.getresponse()
    except (http.client.HTTPException, OSError) as exc:
        connection.close()
        raise LegacyOriginUnavailable("Legacy origin connection failed.") from exc
    return LegacyOriginHandle(connection=connection, response=response)
