"""How a send attempt ended (its outcome and the email's API status) and what kind of error stopped it.

The kinds group failures for the dashboard's error categories: an HTTP answer is grouped by its status and Microsoft's
error code, a request without an answer by what went wrong on the network, and a send stopped by the site itself by
the step it reached.
"""

from apps.core.models import OutboundEmail, OutboundEmailAttempt
from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
)
from apps.core.services.delivery_rates.rules.defaults import signal_patterns
from apps.core.services.delivery_rates.rules.signals import code_in

from ..exceptions import EmailDeliveryError

Outcome = OutboundEmailAttempt.Outcome
Operation = OutboundEmailAttempt.Operation
Status = OutboundEmail.Status

KIND_LABELS = {
    "throttled": "Throttled (HTTP 429)",
    "server_busy": "Service unavailable (HTTP 503 / 509)",
    "auth": "Authentication failure",
    "forbidden": "Access denied (HTTP 403)",
    "mailbox_restricted": "Mailbox restriction",
    "not_found": "Not found (HTTP 404)",
    "bad_request": "Rejected request (HTTP 4xx)",
    "server_error": "Server error (HTTP 5xx)",
    "pushback": "Exchange pushback",
    "quota": "Sending quota exceeded",
    "timeout": "Network timeout",
    "connect_failed": "Connection failed",
    "response_lost": "Response lost",
    "tls": "TLS verification failed",
    "compose": "Message could not be composed",
    "config": "Configuration or mailbox scope",
    "rate_deferred": "Held back by the delivery rate",
    "rate_refused": "Refused by the delivery limits",
    "claim_lost": "Background job claim lost",
    "provider_error": "Provider error",
    "unexpected": "Unexpected error",
}
# Graph error codes that mean the mailbox refuses: send-as denied, not enabled or not reachable through Graph, full.
MAILBOX_RESTRICTION_CODES = (
    "ErrorSendAsDenied",
    "ErrorAccessDenied",
    "MailboxNotEnabledForRESTAPI",
    "MailboxNotSupportedForRESTAPI",
    "ErrorMailboxStoreUnavailable",
    "ErrorQuotaExceeded",
    "ErrorNonExistentMailbox",
)
_OUTCOMES = {
    PROVIDER_OUTCOME_TRANSIENT: Outcome.TRANSIENT,
    PROVIDER_OUTCOME_PERMANENT: Outcome.PERMANENT,
    PROVIDER_OUTCOME_UNCERTAIN: Outcome.UNCERTAIN,
}


def attempt_outcome(exc: BaseException | None, *, entered: bool) -> str:
    """The attempt's outcome: the classified error's retry safety, or for any other exception whether the provider
    call had begun (then it may have been sent)."""
    if exc is None:
        return Outcome.ACCEPTED
    if isinstance(exc, EmailDeliveryError):
        return _OUTCOMES.get(exc.outcome, Outcome.UNCERTAIN)
    return Outcome.UNCERTAIN if entered else Outcome.NOT_SENT


def email_status(outcome: str, *, reached_api: bool) -> str:
    """The email's API status after an attempt: a failure counts as an API failure only when the provider (or its
    token endpoint) was reached or tried; one the site stopped earlier means it was not sent."""
    if outcome == Outcome.ACCEPTED:
        return Status.ACCEPTED
    if outcome == Outcome.UNCERTAIN:
        return Status.UNCERTAIN
    if outcome in (Outcome.TRANSIENT, Outcome.PERMANENT) and reached_api:
        return Status.FAILED
    return Status.NOT_SENT


def error_kind(exc: BaseException | None, notes, *, provider: str = "graph") -> str:
    if exc is None:
        return ""
    if notes.http_status is not None:
        return _http_kind(notes)
    if notes.transport_error:
        return notes.transport_error
    if _claim_lost(exc):
        return "claim_lost"
    if notes.operation == Operation.TOKEN:
        return "auth"
    if notes.operation == Operation.COMPOSE:
        return "compose"
    if provider != "graph" and isinstance(exc, EmailDeliveryError):
        return "provider_error"
    return "unexpected"


def _http_kind(notes) -> str:
    status, code = notes.http_status, notes.inner_error_code or notes.error_code
    patterns = signal_patterns("graph")
    if notes.operation == Operation.TOKEN:
        return "throttled" if status == 429 else ("server_busy" if status >= 500 else "auth")
    if status == 429:
        return "throttled"
    if status in (503, 509):
        return "server_busy"
    if status == 401:
        return "auth"
    if code_in(code, patterns["quota_codes"]):
        return "quota"
    if code_in(code, patterns["pause_codes"]):
        return "pushback"
    if status in patterns["mailbox_full_statuses"] or code_in(code, MAILBOX_RESTRICTION_CODES):
        return "mailbox_restricted"
    if status in (403, 404):
        return "forbidden" if status == 403 else "not_found"
    return "bad_request" if 400 <= status < 500 else "server_error"


def _claim_lost(exc: BaseException) -> bool:
    # Imported here: the background worker imports telemetry, so a module-level import would be a cycle.
    from apps.core.services.background_jobs import JobClaimLost

    return isinstance(exc, JobClaimLost)


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind.replace("_", " ").capitalize() if kind else "")
