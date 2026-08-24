"""Validated SigV4 HTTP transport for the internal status API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from http.client import HTTPResponse
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from .errors import StatusFetchError

MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 8
EXPECTED_INTERNAL_PATH = "/prod/internal/status"


class _RejectRedirects(HTTPRedirectHandler):
    """Prevent a configured AWS endpoint from redirecting to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


def default_opener_factory() -> OpenerDirector:
    return build_opener(_RejectRedirects())


def fetch_status_payload(
    *,
    url: str,
    region: str,
    timeout: int,
    session_factory: Callable[..., Any],
    opener_factory: Callable[[], OpenerDirector],
) -> dict[str, Any]:
    """Validate, sign, execute, and decode one internal API request."""

    validate_endpoint_configuration(url, region)
    request = _signed_request(url=url, region=region, session_factory=session_factory)
    response = opener_factory().open(request, timeout=timeout)
    with response:
        return _decode_response(response)


def validate_endpoint_configuration(url: str, region: str) -> None:
    """Restrict calls to the expected regional API Gateway route."""

    if not url:
        raise StatusFetchError("unconfigured")
    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
        raise StatusFetchError("invalid_configuration")

    try:
        parsed = urlsplit(url)
        parsed_port = parsed.port
    except ValueError:
        raise StatusFetchError("invalid_configuration") from None
    expected_host_suffix = f".execute-api.{region}.amazonaws.com"
    host = (parsed.hostname or "").lower()
    api_id = host.removesuffix(expected_host_suffix) if host.endswith(expected_host_suffix) else ""
    valid_api_id = bool(re.fullmatch(r"[a-z0-9]{8,32}", api_id))
    if not (
        parsed.scheme == "https"
        and valid_api_id
        and parsed.netloc == host
        and parsed_port is None
        and parsed.path == EXPECTED_INTERNAL_PATH
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    ):
        raise StatusFetchError("invalid_configuration")


def http_error_reason(status: int) -> str:
    if 300 <= status < 400:
        return "redirect"
    if status in {401, 403}:
        return "permission"
    if status == 429:
        return "throttled"
    return "upstream" if status >= 500 else "invalid_response"


def _signed_request(*, url: str, region: str, session_factory: Callable[..., Any]) -> Request:
    session = session_factory(region_name=region)
    credentials = session.get_credentials()
    if credentials is None:
        raise StatusFetchError("credentials")
    frozen = credentials.get_frozen_credentials()

    aws_request = AWSRequest(
        method="GET",
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": "i2g-admin-infrastructure-status/1",
        },
    )
    SigV4Auth(frozen, "execute-api", region).add_auth(aws_request)
    prepared = aws_request.prepare()
    return Request(prepared.url, headers=dict(prepared.headers.items()), method="GET")


def _decode_response(response: HTTPResponse) -> dict[str, Any]:
    status = getattr(response, "status", None) or response.getcode()
    if status != 200:
        raise StatusFetchError(http_error_reason(int(status)))

    content_type = str(response.headers.get("Content-Type", "")).partition(";")[0].strip().lower()
    if not (content_type == "application/json" or content_type.endswith("+json")):
        raise StatusFetchError("invalid_response")

    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise StatusFetchError("invalid_response")
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise StatusFetchError("invalid_response") from None
    if not isinstance(decoded, dict):
        raise StatusFetchError("invalid_response")
    return decoded
