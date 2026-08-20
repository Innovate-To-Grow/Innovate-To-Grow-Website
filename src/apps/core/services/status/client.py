"""SigV4 client for the status stack's IAM-protected internal endpoint.

Infrastructure credentials deliberately come from boto3's ambient credential
chain (the ECS task role in production).  The database-backed AWS credential
record is intended for application services such as SES and Bedrock and must
not be reused for operational access.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from http.client import HTTPResponse
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.exceptions import BotoCoreError, NoCredentialsError, PartialCredentialsError
from django.conf import settings

logger = logging.getLogger(__name__)

EXPECTED_SCHEMA_VERSION = 1
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 8
EXPECTED_INTERNAL_PATH = "/prod/internal/status"
MAX_COLLECTION_ITEMS = {
    "errors": 50,
    "resources": 250,
    "services": 50,
    "probes": 100,
    "alarms": 200,
}
MAX_STRING_LENGTH = 4096
MAX_JSON_DEPTH = 12

PUBLIC_ERROR_MESSAGES = {
    "unconfigured": "The infrastructure status connection is not configured.",
    "invalid_configuration": "The infrastructure status connection is configured incorrectly.",
    "credentials": "AWS task-role credentials are unavailable.",
    "permission": "The backend task role cannot read the internal status endpoint.",
    "throttled": "The internal status endpoint is temporarily throttled.",
    "timeout": "The internal status endpoint did not respond in time.",
    "upstream": "The internal status endpoint is temporarily unavailable.",
    "redirect": "The internal status endpoint returned an unexpected redirect.",
    "invalid_response": "The internal status endpoint returned an invalid response.",
    "error": "Infrastructure status could not be loaded.",
}


class StatusFetchError(RuntimeError):
    """A sanitized internal-status failure safe to expose in the admin UI."""

    def __init__(self, reason: str):
        normalized = reason if reason in PUBLIC_ERROR_MESSAGES else "error"
        self.reason = normalized
        self.public_message = PUBLIC_ERROR_MESSAGES[normalized]
        super().__init__(self.public_message)


class _RejectRedirects(HTTPRedirectHandler):
    """Prevent a configured AWS endpoint from redirecting to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


def _default_opener_factory() -> OpenerDirector:
    return build_opener(_RejectRedirects())


class InternalStatusApiClient:
    """Fetch and validate one live infrastructure payload from API Gateway."""

    def __init__(
        self,
        *,
        url: str | None = None,
        region: str | None = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        session_factory: Callable[..., Any] | None = None,
        opener_factory: Callable[[], OpenerDirector] | None = None,
    ):
        self.region = (
            region or getattr(settings, "STATUS_API_REGION", "") or getattr(settings, "AWS_REGION", "") or "us-west-2"
        ).strip()
        self.url = (url if url is not None else getattr(settings, "STATUS_INTERNAL_API_URL", "")).strip()
        self.timeout = timeout
        self._session_factory = session_factory or boto3.Session
        self._opener_factory = opener_factory or _default_opener_factory

    def fetch(self) -> dict[str, Any]:
        """Return a validated schema-v1 payload or raise ``StatusFetchError``."""

        self._validate_configuration()
        try:
            request = self._signed_request()
            response = self._opener_factory().open(request, timeout=self.timeout)
            with response:
                payload = self._decode_response(response)
        except StatusFetchError:
            raise
        except HTTPError as exc:
            reason = _http_error_reason(exc.code)
            logger.warning("Internal status API request failed (reason=%s, status=%s)", reason, exc.code)
            raise StatusFetchError(reason) from None
        except TimeoutError:
            logger.warning("Internal status API request timed out")
            raise StatusFetchError("timeout") from None
        except URLError as exc:
            reason = "timeout" if isinstance(exc.reason, TimeoutError) else "upstream"
            logger.warning("Internal status API transport failed (reason=%s)", reason)
            raise StatusFetchError(reason) from None
        except (NoCredentialsError, PartialCredentialsError):
            logger.warning("Ambient AWS credentials are unavailable for the internal status API")
            raise StatusFetchError("credentials") from None
        except BotoCoreError:
            logger.warning("AWS request signing failed for the internal status API")
            raise StatusFetchError("credentials") from None
        except Exception:  # noqa: BLE001 -- admin dashboards must degrade instead of returning HTTP 500.
            # Transport exceptions may include signed headers or upstream
            # details, so log only the sanitized failure category.
            logger.error("Unexpected internal status API failure")
            raise StatusFetchError("error") from None

        validate_status_payload(payload)
        return payload

    def _validate_configuration(self) -> None:
        if not self.url:
            raise StatusFetchError("unconfigured")
        if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", self.region):
            raise StatusFetchError("invalid_configuration")

        try:
            parsed = urlsplit(self.url)
            parsed_port = parsed.port
        except ValueError:
            raise StatusFetchError("invalid_configuration") from None
        expected_host_suffix = f".execute-api.{self.region}.amazonaws.com"
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

    def _signed_request(self) -> Request:
        session = self._session_factory(region_name=self.region)
        credentials = session.get_credentials()
        if credentials is None:
            raise StatusFetchError("credentials")
        frozen = credentials.get_frozen_credentials()

        aws_request = AWSRequest(
            method="GET",
            url=self.url,
            headers={
                "Accept": "application/json",
                "User-Agent": "i2g-admin-infrastructure-status/1",
            },
        )
        SigV4Auth(frozen, "execute-api", self.region).add_auth(aws_request)
        prepared = aws_request.prepare()
        return Request(prepared.url, headers=dict(prepared.headers.items()), method="GET")

    @staticmethod
    def _decode_response(response: HTTPResponse) -> dict[str, Any]:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise StatusFetchError(_http_error_reason(int(status)))

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


def _http_error_reason(status: int) -> str:
    if 300 <= status < 400:
        return "redirect"
    if status in {401, 403}:
        return "permission"
    if status == 429:
        return "throttled"
    return "upstream" if status >= 500 else "invalid_response"
