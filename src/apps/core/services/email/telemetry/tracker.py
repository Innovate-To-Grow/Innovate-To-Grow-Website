"""The delivery facade's telemetry: one ``DeliveryTracker`` around each ``EmailDeliveryService.send`` call.

It opens (or, for a retry, finds) the logical email first, opens one attempt once the message is admitted, and
closes them from the outcome: the exception the facade raises and what the provider noted on the way (for Microsoft
Graph, the step it reached, the HTTP status, Microsoft's error code and request ids). It never raises into the
facade and never swallows the facade's exception, so sending behaves exactly as without it.
"""

import logging
import time

from django.utils import timezone

from ..exceptions import EmailDeliveryError, EmailRateDeferred
from . import classify, recorder, text
from .context import current_tracking
from .notes import AttemptNotes, collecting

logger = logging.getLogger(__name__)

RESOLVE, ADMIT, ATTEMPT = "resolve", "admit", "attempt"


def safe_error(exc: BaseException | None) -> str:
    """A storable description of ``exc``: the site's own classified messages (scrubbed), else the type name only."""
    if exc is None:
        return ""
    if isinstance(exc, EmailDeliveryError) or classify.error_kind(exc, AttemptNotes()) == "claim_lost":
        return text.scrub(str(exc))
    return f"Unexpected {type(exc).__name__}"


class DeliveryTracker:
    def __init__(self, message, *, provider: str):
        self.message = message
        self.provider = str(provider or "").strip().lower()
        self.context = current_tracking()
        self.notes = AttemptNotes()
        self.phase = RESOLVE
        self.mailbox = ""
        self.email_id = None
        self.attempt_id = None
        self._boundary = None
        self._started = 0.0
        self._collecting = None

    def __enter__(self):
        if recorder.enabled():
            self.email_id = recorder.open_email(self.message, self.context, provider=self.provider)
        self._collecting = collecting(self.notes)
        self._collecting.__enter__()
        return self

    def resolved(self, provider) -> None:
        """The configured provider was built (the configuration and mailbox scope allow the send)."""
        self.phase = ADMIT
        self.provider = str(getattr(provider, "name", "") or self.provider)
        self.mailbox = str(getattr(provider, "mailbox", "") or "")

    def attempting(self, boundary) -> None:
        """The delivery rate admitted the message; the provider call starts now."""
        self.phase = ATTEMPT
        self._boundary = boundary
        self._started = time.monotonic()
        if self.email_id is not None:
            self.attempt_id = recorder.open_attempt(
                self.email_id,
                provider=self.provider,
                mailbox=self.mailbox,
                job_attempt=self.context.job_attempt,
                started_at=timezone.now(),
            )

    def __exit__(self, exc_type, exc, traceback):
        self._collecting.__exit__(exc_type, exc, traceback)
        if self.email_id is not None:
            try:
                self._close(exc)
            except Exception as error:  # noqa: BLE001 - telemetry must never change delivery.
                logger.warning("Email telemetry could not be closed (%s)", type(error).__name__)
        return False

    def _close(self, exc) -> None:
        if self.phase == ATTEMPT:
            if self.attempt_id is not None:
                self._close_attempt(exc)
        elif isinstance(exc, EmailRateDeferred):
            recorder.record_deferral(self.email_id, retry_expected=bool(self.context.retry_key), error=safe_error(exc))
        elif exc is not None:
            kind = "config" if self.phase == RESOLVE else "rate_refused"
            recorder.record_unsent(self.email_id, kind=kind, error=safe_error(exc))

    def _close_attempt(self, exc) -> None:
        notes = self.notes
        entered = bool(getattr(self._boundary, "entered", False))
        outcome = classify.attempt_outcome(exc, entered=entered)
        reached_api = entered or notes.http_status is not None or bool(notes.transport_error)
        recorder.close_attempt(
            self.email_id,
            self.attempt_id,
            outcome=outcome,
            status=classify.email_status(outcome, reached_api=reached_api),
            kind=classify.error_kind(exc, notes, provider=self.provider),
            error=safe_error(exc),
            notes=notes,
            duration_ms=max(0, round((time.monotonic() - self._started) * 1000)),
        )
