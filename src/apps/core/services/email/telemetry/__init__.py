"""Telemetry of every outgoing email, recorded by the delivery facade so no sender can bypass it.

- ``context``: what a sender knows (category, campaign, source record, retry key), set with ``email_tracking``; the
  background worker sets the job (``job_tracking``) so a job's retries share one logical email.
- ``notes``: what a provider learned during one attempt (Microsoft Graph: step, HTTP status, error codes, request
  ids, Retry-After, response time), collected in memory.
- ``tracker``: ``DeliveryTracker``, the facade's wrapper that saves the email and its attempts (``recorder``) and
  classifies the outcome (``classify``).
- ``probes``: the access check's probe emails, which bypass the facade; ``retention``: the maintenance purge.

A new email feature that sends through ``deliver_email`` is recorded without any change (category "other"); wrapping
its send in ``email_tracking(category=...)`` files it under its own category.
"""

from .classify import KIND_LABELS, kind_label
from .context import TrackingContext, current_tracking, email_tracking, job_tracking
from .notes import AttemptNotes, current_notes
from .tracker import DeliveryTracker

__all__ = [
    "KIND_LABELS",
    "AttemptNotes",
    "DeliveryTracker",
    "TrackingContext",
    "current_notes",
    "current_tracking",
    "email_tracking",
    "job_tracking",
    "kind_label",
]
