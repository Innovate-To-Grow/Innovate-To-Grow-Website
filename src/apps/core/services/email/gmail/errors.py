"""Map Google token-endpoint and Gmail API failures to classified email delivery errors.

Messages are fixed text plus, at most, an allow-listed error code; a response body or Google's free text is never
echoed or stored, only matched against fixed patterns. Each error carries the rate signal of Google's answer
(``delivery_rates.adapters.gmail_api``).
"""

import json
import re

from apps.core.services.delivery_rates import SignalKind, code_in
from apps.core.services.delivery_rates.adapters.gmail_api import retry_after, send_signal, token_signal
from apps.core.services.delivery_rates.rules.defaults import signal_patterns

from ..exceptions import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    with_signal,
)
from ..transport import HttpResponse

_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,63}")
# Documented Gmail API and Google error reasons besides the rate-relevant ones in the settings' signal patterns:
# only these (and those) are ever shown or logged. https://developers.google.com/workspace/gmail/api/guides/handle-errors
# and https://cloud.google.com/apis/design/errors (the canonical status codes).
_SHOWN_REASONS = (
    "authError",
    "backendError",
    "forbidden",
    "insufficientPermissions",
    "invalid",
    "notFound",
    "required",
    "INTERNAL",
    "NOT_FOUND",
    "PERMISSION_DENIED",
    "RESOURCE_EXHAUSTED",
    "UNAUTHENTICATED",
    "UNAVAILABLE",
)
_MAX_MATCHED_TEXT = 512
UNAUTHORIZED_CLIENT = "unauthorized_client"
ACCESS_DENIED = "access_denied"
# Delegation not (yet) granted: on a first install the key is kept, because the Workspace admin may still be
# adding the client ("Changes can take up to 24 hours").
DELEGATION_PENDING_CODES = frozenset({UNAUTHORIZED_CLIENT, ACCESS_DENIED})
# Google's documented ``invalid_grant`` descriptions (OAuth 2.0 for service accounts, error codes table): matched to
# explain the cause, never shown.
_INVALID_GRANT_CAUSES = (
    (("Not a valid email", "Invalid email or User ID"), "the account does not exist in the Workspace domain"),
    (("Invalid JWT Signature",), "the key was deleted or belongs to another service account"),
    (("Token must be a short-lived token",), "the assertion's time is off; check the server clock"),
)
_TOKEN_CAUSES = {
    UNAUTHORIZED_CLIENT: (
        "the Workspace admin has not authorized numeric client ID {client_id} for gmail.send, removed it, or added "
        "the client by email instead of the numeric ID. Changes can take up to 24 hours"
    ),
    ACCESS_DENIED: "gmail.send is not authorized for client ID {client_id} in the Admin console",
    "admin_policy_enforced": "a Workspace administrator policy blocks this scope",
    "disabled_client": "the signing key or the service account is disabled",
    "invalid_client": "Google does not know this service account",
    "deleted_client": "the service account was deleted",
    "org_internal": "the project's OAuth client is limited to another organization",
    "invalid_scope": "the requested scope is not valid",
}


class GmailTokenRefused(PermanentEmailDeliveryError):
    """Google refused the token request. ``code`` is the allow-listed OAuth error (or ""), for the install and the
    access check to tell a pending delegation from a key that does not work."""

    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code


def _json_object(body: bytes) -> dict:
    try:
        data = json.loads(body) if body else {}
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def _safe_code(value) -> str:
    return value if isinstance(value, str) and _CODE_RE.fullmatch(value) else ""


def _known(code: str, *groups) -> str:
    """*code* when it is one of the documented codes in *groups* (settings keys or tuples), else ""."""
    patterns = signal_patterns("gmail_api")
    known = [item for group in groups for item in (patterns[group] if isinstance(group, str) else group)]
    return code if code_in(code, known) else ""


def shown_reason(reason: str) -> str:
    """A send error reason Google documents, for messages and logs; anything else is never echoed."""
    groups = ("throttle_reasons", "daily_quota_reasons", "blocked_reasons", "message_reasons", _SHOWN_REASONS)
    return _known(reason, *groups)


def _text(value) -> str:
    return value[:_MAX_MATCHED_TEXT] if isinstance(value, str) else ""


def token_error(response: HttpResponse, *, client_id: str) -> Exception:
    """The error for a non-200 token answer. No mail was sent, so retry safety is always certain."""
    data = _json_object(response.body)
    code = _known(_safe_code(data.get("error")), "token_pause_codes", "token_blocked_codes")
    signal = token_signal(response.status, response.headers, code)
    if signal.kind == SignalKind.PAUSE:
        error = TransientEmailDeliveryError(
            "Google's token endpoint is temporarily unavailable.", retry_after=signal.retry_after
        )
        return with_signal(error, signal)
    cause = _TOKEN_CAUSES.get(code, "")
    if code == "invalid_grant":
        description = _text(data.get("error_description"))
        cause = next((text for needles, text in _INVALID_GRANT_CAUSES if any(n in description for n in needles)), "")
    detail = f" ({code})" if code else ""
    message = f"Google rejected the Gmail API credentials{detail}"
    if cause:
        message = f"{message}: {cause.format(client_id=client_id or 'unknown')}"
    return with_signal(GmailTokenRefused(f"{message}.", code=code), signal)


def error_reason(body: bytes) -> tuple[str, str]:
    """The allow-listed reason of a Gmail error body and its message (for matching only).

    The reason is read from the legacy ``error.errors[0].reason``, an ErrorInfo ``reason`` in ``error.details``,
    then ``error.status``.
    """
    error = _json_object(body).get("error")
    if not isinstance(error, dict):
        return "", ""
    reasons = []
    legacy = error.get("errors")
    if isinstance(legacy, list) and legacy and isinstance(legacy[0], dict):
        reasons.append(legacy[0].get("reason"))
    details = error.get("details")
    if isinstance(details, list):
        reasons.extend(item.get("reason") for item in details if isinstance(item, dict))
    reasons.append(error.get("status"))
    reason = next((code for code in map(_safe_code, reasons) if code), "")
    return reason, _text(error.get("message"))


def send_error(response: HttpResponse, *, fresh_token: bool) -> Exception:
    """The error for a ``messages.send`` answer other than 200, with the rate signal of the answer."""
    reason, message = error_reason(response.body)
    signal = send_signal(response.status, response.headers, reason, message, fresh_token=fresh_token)
    detail = f" ({shown_reason(reason)})" if shown_reason(reason) else ""
    status = response.status
    if signal.kind in (SignalKind.THROTTLE, SignalKind.QUOTA, SignalKind.PAUSE):
        wait = signal.retry_after or signal.breaker_seconds or retry_after(response.headers, message)
        error = TransientEmailDeliveryError(f"The Gmail API asked the site to slow down{detail}.", retry_after=wait)
    elif status == 401 and not fresh_token:
        error = TransientEmailDeliveryError("The Gmail API rejected the access token; it will be refreshed.")
    elif 400 <= status < 500:
        error = PermanentEmailDeliveryError(f"The Gmail API rejected the message (HTTP {status}){detail}.")
    else:
        # No documented "not processed" meaning, and messages.send has no idempotency key: never assume "not sent".
        error = UncertainEmailDeliveryError(
            f"The Gmail API returned HTTP {status}; delivery could not be confirmed{detail}."
        )
    return with_signal(error, signal)
