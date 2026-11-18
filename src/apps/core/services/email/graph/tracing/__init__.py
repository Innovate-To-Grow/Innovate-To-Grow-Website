"""Microsoft Graph Message Trace delivery status (opt-in: the Graph config's ``message_trace_enabled``, off by
default; it needs the tenant-wide ``ExchangeMessageTrace.Read.All`` permission, which is beyond the InfoSec approval).

``reader`` reads one sender's trace (GET only, the sender filter required by the transport's allow-list), ``matching``
pairs its rows with the outgoing emails, ``windows`` writes their delivery statuses within a run's request budget,
``sync`` holds the gates, lease, token-roles pre-check and backoff (``state``), ``jobs`` runs it in the worker, and
``limits`` holds its bounded ``EMAIL_MONITORING`` values.
"""

from .jobs import DELIVERY_TRACE_JOB_KIND, ensure_scheduled, purge_finished_jobs, register_trace_jobs, run_now
from .sync import TraceOutcome, sync_delivery

__all__ = [
    "DELIVERY_TRACE_JOB_KIND",
    "TraceOutcome",
    "ensure_scheduled",
    "purge_finished_jobs",
    "register_trace_jobs",
    "run_now",
    "sync_delivery",
]
