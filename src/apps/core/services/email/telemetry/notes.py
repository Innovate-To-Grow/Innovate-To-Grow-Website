"""What one provider attempt learned, kept in memory until the delivery tracker saves it.

The Graph provider and its token code note each step (``current_notes().step(...)``) and each answer. Outside a
tracked send (a provider used directly) ``current_notes()`` returns a throwaway object, so providers never check
whether telemetry is on. Only allow-listed, length-bounded values are kept: never a token, a body or free text.
"""

import contextvars
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from ..transport import ConnectFailed

# The steps of a Graph attempt (``OutboundEmailAttempt.Operation`` values), named here so providers need no model.
COMPOSE, TOKEN, SEND_MAIL = "compose", "token", "send_mail"
SEND_MAIL_ENDPOINT = "POST /v1.0/users/{mailbox}/sendMail"
IDENTITY_ENDPOINT = "POST /{tenant}/oauth2/v2.0/token"

# Microsoft's diagnostic response headers (data centre, throttle scope): non-secret, and what Microsoft support asks
# for alongside the request id.
DIAGNOSTIC_HEADERS = (
    "x-ms-ags-diagnostic",
    "x-ms-throttle-scope",
    "x-ms-throttle-information",
    "x-ms-throttle-limit-percentage",
    "x-ms-resource-unit",
)
_SAFE_HEADER_VALUE = re.compile(r"[\x20-\x7e]{1,256}")


def diagnostic_headers(headers: dict) -> dict:
    """The allow-listed diagnostic headers whose values are short printable ASCII."""
    kept = {}
    for name in DIAGNOSTIC_HEADERS:
        value = str(headers.get(name) or "")
        if _SAFE_HEADER_VALUE.fullmatch(value):
            kept[name] = value
    return kept


def transport_failure_kind(exc: BaseException) -> str:
    """``tls``, ``timeout``, ``connect_failed`` (nothing was sent) or ``response_lost`` (it may have been)."""
    if isinstance(exc, ConnectFailed) and exc.verification_failed:
        return "tls"
    if isinstance(exc.__cause__, TimeoutError):
        return "timeout"
    return "connect_failed" if isinstance(exc, ConnectFailed) else "response_lost"


@dataclass
class AttemptNotes:
    operation: str = ""
    endpoint: str = ""
    send_format: str = ""
    internet_message_id: str = ""
    token_fresh: bool | None = None
    http_status: int | None = None
    error_code: str = ""
    inner_error_code: str = ""
    request_id: str = ""
    client_request_id: str = ""
    retry_after_seconds: int | None = None
    transport_error: str = ""
    response_ms: int | None = None
    diagnostics: dict = field(default_factory=dict)
    request_started: float | None = None

    def step(self, operation: str, endpoint: str = "") -> None:
        """The attempt moved on to ``operation``: what an earlier step answered no longer says where it stands."""
        self.operation, self.endpoint = operation, endpoint
        self.http_status = self.retry_after_seconds = self.response_ms = None
        self.error_code = self.inner_error_code = self.request_id = self.client_request_id = ""
        self.transport_error = ""
        self.diagnostics = {}
        self.request_started = time.monotonic()

    def new_client_request_id(self) -> str:
        """A fresh ``client-request-id`` GUID for the request about to be made (Microsoft logs it with the request)."""
        self.client_request_id = str(uuid.uuid4())
        return self.client_request_id

    def message(self, *, send_format: str, internet_message_id: str = "") -> None:
        self.send_format, self.internet_message_id = send_format, internet_message_id

    def answered(self, *, http_status: int, headers: dict | None = None, retry_after_seconds=None, **codes) -> None:
        """Microsoft answered: ``codes`` are the allow-listed ``error_code`` / ``inner_error_code`` / ``request_id`` /
        ``client_request_id`` values the caller already parsed."""
        self.http_status = http_status
        self.retry_after_seconds = int(retry_after_seconds) if retry_after_seconds is not None else None
        for name in ("error_code", "inner_error_code", "request_id", "client_request_id"):
            if codes.get(name):
                setattr(self, name, str(codes[name])[:64])
        self.diagnostics = diagnostic_headers(headers or {})
        self.response_ms = self._elapsed_ms()

    def transport_failed(self, exc: BaseException) -> None:
        self.transport_error = transport_failure_kind(exc)
        self.response_ms = self._elapsed_ms()

    def _elapsed_ms(self) -> int | None:
        if self.request_started is None:
            return None
        return max(0, round((time.monotonic() - self.request_started) * 1000))


_current: contextvars.ContextVar[AttemptNotes | None] = contextvars.ContextVar("email_attempt_notes", default=None)


def current_notes() -> AttemptNotes:
    """The notes of the attempt in progress, or a throwaway object outside a tracked send."""
    notes = _current.get()
    return notes if notes is not None else AttemptNotes()


@contextmanager
def collecting(notes: AttemptNotes):
    token = _current.set(notes)
    try:
        yield notes
    finally:
        _current.reset(token)
