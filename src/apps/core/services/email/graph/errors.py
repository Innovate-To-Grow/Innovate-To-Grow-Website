"""Map Microsoft identity-platform and Graph HTTP failures to classified email delivery errors.

Messages are generic and carry only an allow-listed error code, never a response body. Each error also carries
the rate signal of Microsoft's answer (``delivery_rates.adapters.graph``).
"""

import json
import re

from django.conf import settings

from apps.core.services.delivery_rates.adapters.graph import graph_signal, pushback, token_signal
from apps.core.services.delivery_rates.rules.defaults import signal_patterns

from ..exceptions import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    with_signal,
)
from .transport import HttpResponse

_RETRY_AFTER_RE = re.compile(r"[0-9]{1,9}")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,63}")
_REQUEST_ID_RE = re.compile(r"[0-9A-Za-z-]{8,64}")
# 408 is the generic HTTP "server gave up waiting for the request".
_REQUEST_TIMEOUT = 408


def retryable(status: int) -> bool:
    """Throttling and temporary unavailability (``DELIVERY_RATES["signals"]["graph"]["throttle_statuses"]``, and
    408): Microsoft documents repeating the request after a delay. Sends and mailbox reads share this rule."""
    return status == _REQUEST_TIMEOUT or status in signal_patterns("graph")["throttle_statuses"]


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


def _error_codes(body: bytes) -> tuple[str, str]:
    error = _json_object(body).get("error")
    if not isinstance(error, dict):
        return "", ""
    inner = error.get("innerError") or error.get("innererror")
    inner_code = _safe_code(inner.get("code")) if isinstance(inner, dict) else ""
    return _safe_code(error.get("code")), inner_code


def graph_error_code(body: bytes) -> str:
    """The allow-listed ``error.code`` of a Graph error body (falling back to ``innerError.code``), for messages."""
    outer, inner = _error_codes(body)
    return outer or inner


def innermost_error_code(body: bytes) -> str:
    """The most specific allow-listed code (``innerError.code``, else ``error.code``): what rate signals match."""
    outer, inner = _error_codes(body)
    return inner or outer


def identity_error_code(body: bytes) -> str:
    """The allow-listed OAuth ``error`` plus its first AADSTS number from an identity-platform error body."""
    data = _json_object(body)
    code = _safe_code(data.get("error"))
    numbers = data.get("error_codes")
    if isinstance(numbers, list) and numbers and type(numbers[0]) is int and 0 < numbers[0] < 10**8:
        return f"{code} AADSTS{numbers[0]}".strip()
    return code


def token_endpoint_error(response: HttpResponse) -> Exception:
    """The error for a non-200 token response. No mail was sent, so retry safety is always certain.

    Its rate signal pauses Graph for the mailbox while the identity platform is busy, and stops it (until the
    configuration is saved, or a timed probe) when the credentials are refused.
    """
    code = identity_error_code(response.body)
    busy = retryable(response.status) or response.status >= 500
    signal = token_signal(response.status, response.headers, code, retryable=busy)
    if busy:
        error = TransientEmailDeliveryError(
            "Microsoft identity platform is temporarily unavailable.",
            retry_after=retry_after_seconds(response.headers),
        )
        return with_signal(error, signal)
    detail = f" ({code})" if code else ""
    return with_signal(PermanentEmailDeliveryError(f"Microsoft rejected the Graph credentials{detail}."), signal)


def send_mail_error(response: HttpResponse, *, fresh_token: bool = False) -> Exception:
    """The error for a sendMail response other than ``202 Accepted``, with the rate signal of the answer.

    ``fresh_token``: the access token was issued for this send, so a 401 means the grant is refused (an auth stop
    in the signal), not an expired token. The error is PR #643's either way (transient, the token dropped): a queued
    message waits for the stop to clear.
    """
    code = innermost_error_code(response.body)
    signal = graph_signal(response.status, response.headers, code, fresh_token=fresh_token)
    return with_signal(_send_mail_error(response), signal)


def _send_mail_error(response: HttpResponse) -> Exception:
    status = response.status
    if retryable(status):
        return TransientEmailDeliveryError(
            "Microsoft Graph temporarily rejected the request.",
            retry_after=retry_after_seconds(response.headers),
        )
    if status == 401:
        return TransientEmailDeliveryError("Microsoft Graph rejected the access token; it will be refreshed.")
    code = graph_error_code(response.body)
    detail = f" ({code})" if code else ""
    if pushback(innermost_error_code(response.body)):
        # Exchange pushed back without a throttle status: the message may still have been accepted.
        return UncertainEmailDeliveryError(
            f"Microsoft Graph pushed back on the request{detail}; it may have been sent."
        )
    if status == 507:
        return PermanentEmailDeliveryError("The sender mailbox is full (HTTP 507); free space in the mailbox.")
    if 400 <= status < 500:
        return PermanentEmailDeliveryError(f"Microsoft Graph rejected the request{detail}.")
    # Other 5xx can follow acceptance (gateway errors) and any other status is unexpected: never assume "not sent".
    return UncertainEmailDeliveryError(
        f"Microsoft Graph returned HTTP {status}; delivery could not be confirmed{detail}."
    )
