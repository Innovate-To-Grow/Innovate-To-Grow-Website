"""Map Microsoft identity-platform and Graph HTTP failures to classified email delivery errors.

Messages are generic and carry only an allow-listed error code, never a response body.
"""

import json
import re

from django.conf import settings

from ..exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError, UncertainEmailDeliveryError
from .transport import HttpResponse

_RETRY_AFTER_RE = re.compile(r"[0-9]{1,9}")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,63}")
_REQUEST_ID_RE = re.compile(r"[0-9A-Za-z-]{8,64}")
# Throttling and temporary unavailability: Microsoft documents repeating the request after a delay (408 is the
# generic HTTP "server gave up waiting for the request" equivalent).
_RETRYABLE_STATUSES = {408, 429, 503}


def retry_after_seconds(headers: dict[str, str]) -> float | None:
    """The ``Retry-After`` delay in whole seconds (capped at ``GRAPH_MAX_RETRY_AFTER_SECONDS``), or None when absent
    or not a plain number."""
    raw = headers.get("retry-after", "").strip()
    if not _RETRY_AFTER_RE.fullmatch(raw):
        return None
    return float(min(int(raw), settings.GRAPH_MAX_RETRY_AFTER_SECONDS))


def request_id(headers: dict[str, str]) -> str:
    """The sanitized Microsoft correlation id for log lines, or an empty string."""
    value = headers.get("request-id") or headers.get("client-request-id") or ""
    return value if _REQUEST_ID_RE.fullmatch(value) else ""


def _json_object(body: bytes) -> dict:
    try:
        data = json.loads(body) if body else {}
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def _safe_code(value) -> str:
    return value if isinstance(value, str) and _CODE_RE.fullmatch(value) else ""


def graph_error_code(body: bytes) -> str:
    """The allow-listed ``error.code`` of a Graph error body (falling back to ``innerError.code``)."""
    error = _json_object(body).get("error")
    if not isinstance(error, dict):
        return ""
    inner = error.get("innerError") or error.get("innererror")
    inner_code = _safe_code(inner.get("code")) if isinstance(inner, dict) else ""
    return _safe_code(error.get("code")) or inner_code


def identity_error_code(body: bytes) -> str:
    """The allow-listed OAuth ``error`` plus its first AADSTS number from an identity-platform error body."""
    data = _json_object(body)
    code = _safe_code(data.get("error"))
    numbers = data.get("error_codes")
    if isinstance(numbers, list) and numbers and type(numbers[0]) is int and 0 < numbers[0] < 10**8:
        return f"{code} AADSTS{numbers[0]}".strip()
    return code


def token_endpoint_error(response: HttpResponse) -> Exception:
    """The error for a non-200 token response. No mail was sent, so retry safety is always certain."""
    if response.status in _RETRYABLE_STATUSES or response.status >= 500:
        return TransientEmailDeliveryError(
            "Microsoft identity platform is temporarily unavailable.",
            retry_after=retry_after_seconds(response.headers),
        )
    code = identity_error_code(response.body)
    detail = f" ({code})" if code else ""
    return PermanentEmailDeliveryError(f"Microsoft rejected the Graph credentials{detail}.")


def send_mail_error(response: HttpResponse) -> Exception:
    """The error for a sendMail response other than ``202 Accepted``."""
    status = response.status
    if status in _RETRYABLE_STATUSES:
        return TransientEmailDeliveryError(
            "Microsoft Graph temporarily rejected the request.",
            retry_after=retry_after_seconds(response.headers),
        )
    if status == 401:
        return TransientEmailDeliveryError("Microsoft Graph rejected the access token; it will be refreshed.")
    code = graph_error_code(response.body)
    detail = f" ({code})" if code else ""
    if status == 507:
        return PermanentEmailDeliveryError("The sender mailbox is full (HTTP 507); free space in the mailbox.")
    if 400 <= status < 500:
        return PermanentEmailDeliveryError(f"Microsoft Graph rejected the request{detail}.")
    # Other 5xx can follow acceptance (gateway errors) and any other status is unexpected: never assume "not sent".
    return UncertainEmailDeliveryError(
        f"Microsoft Graph returned HTTP {status}; delivery could not be confirmed{detail}."
    )
