"""What the sender knows about an outgoing email, carried to the delivery facade without changing any signature.

A sender wraps its send in ``email_tracking(category=..., campaign_id=..., retry_key=...)``; nested blocks merge, the
inner value winning field by field. The background worker opens one around every job (``job_tracking``), so the email
of a job that runs again lands on the same logical email: its retry key is the job. A campaign recipient's key is its
recipient log, which also covers the in-process runner's resends. Nothing here touches the database.
"""

import contextvars
import hashlib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace

# Namespace of the correlation ids derived from retry keys (uuid5): every process derives the same id for one email.
CORRELATION_NAMESPACE = uuid.UUID("5b0e4f4e-2c4d-4e0f-9a43-3f1d8f6c2a71")


@dataclass(frozen=True)
class TrackingContext:
    category: str = ""
    subcategory: str = ""
    campaign_id: str = ""
    source_type: str = ""
    source_id: str = ""
    job_id: str = ""
    job_kind: str = ""
    job_attempt: int | None = None
    retry_key: str = ""


_EMPTY = TrackingContext()
_current: contextvars.ContextVar[TrackingContext | None] = contextvars.ContextVar("email_tracking", default=None)


def current_tracking() -> TrackingContext:
    return _current.get() or _EMPTY


def _value(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else str(value)


@contextmanager
def email_tracking(**values):
    """Annotate every email sent inside the block. ``None`` and ``""`` keep the outer value; an unknown field name
    is a programming error (``TypeError``)."""
    changes = {name: _value(value) for name, value in values.items() if value is not None and value != ""}
    token = _current.set(replace(current_tracking(), **changes))
    try:
        yield current_tracking()
    finally:
        _current.reset(token)


def job_tracking(job):
    """The block a background job runs in: its id, kind and attempt, with the job as the retry key."""
    return email_tracking(
        job_id=job.pk, job_kind=job.kind, job_attempt=job.attempts, retry_key=f"core.backgroundjob:{job.pk}"
    )


def correlation_id(context: TrackingContext, recipients, subject: str) -> uuid.UUID:
    """The same id for every attempt at one email when the context names a retry key, a new one otherwise.

    The recipients and the subject are part of the derivation, so two different emails sent under one key never merge.
    """
    if not context.retry_key:
        return uuid.uuid4()
    material = "\n".join((context.retry_key, ",".join(sorted(recipients)), subject or ""))
    return uuid.uuid5(CORRELATION_NAMESPACE, hashlib.sha256(material.encode("utf-8")).hexdigest())
