"""Telemetry of the Microsoft Graph access check's probe emails, which bypass the delivery facade.

The probe that Microsoft should allow sends a real email to the scoped mailbox; the probes it must refuse send one
only if the mailbox restriction is broken. Each send that reached Microsoft (or may have) is recorded as a logical
email of category "access_check" with one attempt; the dashboard lists them but leaves them out of its totals.
"""

import functools

from django.utils import timezone

from apps.core.models import EmailCategory, OutboundEmail, OutboundEmailAttempt

from . import recorder, text

Outcome = OutboundEmailAttempt.Outcome


def _result_outcome(result) -> tuple[str, str] | None:
    """``(attempt outcome, email status)`` of a probe result, or None when no request was made."""
    from ..graph.access_check.probes import OUTCOME_UNKNOWN, UNREACHABLE  # the probes import this module

    if result.status == 202:
        return Outcome.ACCEPTED, OutboundEmail.Status.ACCEPTED
    if result.status is not None or result.note == UNREACHABLE:
        return Outcome.PERMANENT, OutboundEmail.Status.FAILED
    if result.note == OUTCOME_UNKNOWN:
        return Outcome.UNCERTAIN, OutboundEmail.Status.UNCERTAIN
    return None


@recorder.best_effort
def record_probe_send(result, *, recipient: str, send_format: str, subject: str) -> None:
    outcome = _result_outcome(result)
    if outcome is None or not recorder.enabled():
        return
    now = timezone.now()
    accepted = outcome[1] == OutboundEmail.Status.ACCEPTED
    address = text.address(recipient)
    email = OutboundEmail.objects.create(
        category=EmailCategory.ACCESS_CHECK,
        subcategory=text.clean(result.check, 100),
        provider="graph",
        mailbox=text.clean(result.mailbox, 254),
        recipient=address,
        recipients=[address] if address else [],
        recipient_count=1 if address else 0,
        subject=text.clean(subject, 255),
        subject_digest=text.subject_digest(subject),
        send_format=send_format,
        status=outcome[1],
        delivery_status=(
            OutboundEmail.DeliveryStatus.UNKNOWN if accepted else OutboundEmail.DeliveryStatus.NOT_APPLICABLE
        ),
        attempt_count=1,
        first_attempt_at=now,
        last_attempt_at=now,
        accepted_at=now if accepted else None,
        last_http_status=result.status,
        last_error_code="" if accepted else text.clean(result.code, 64),
        last_error="" if accepted else text.scrub(result.note),
    )
    OutboundEmailAttempt.objects.create(
        email=email,
        attempt_number=1,
        provider="graph",
        operation=OutboundEmailAttempt.Operation.PROBE,
        endpoint="POST /v1.0/users/{mailbox}/sendMail",
        outcome=outcome[0],
        http_status=result.status,
        error_code="" if accepted else text.clean(result.code, 64),
        error_message="" if accepted else text.scrub(result.note),
        request_id=text.clean(result.request_id, 64),
        started_at=now,
    )


def tracked_probe(send_format: str, subject: str):
    """Decorator for a ``Prober`` send method: record the probe it sent (recipient: the ``recipient`` keyword, else
    the first positional argument, the mailbox that sends to itself)."""

    def decorate(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            result = method(self, *args, **kwargs)
            recipient = kwargs.get("recipient") or (args[0] if args else "")
            record_probe_send(result, recipient=recipient, send_format=send_format, subject=subject)
            return result

        return wrapper

    return decorate
