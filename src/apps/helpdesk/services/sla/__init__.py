"""Service levels, ServiceNow style: the priority from impact and urgency (``priority``), each ticket's SLA clock
(``clock``: due times, pausing, the first response), how a clock reads (``display``), the breached / at-risk queue
filters and the worker's breach marking (``breaches``), and the scheduled auto-close of resolved tickets
(``automation``, imported by the worker only: it works through ``tickets.changes``)."""

from .breaches import at_risk_q, breached_q, mark_breaches
from .clock import (
    RUNNING_STATUSES,
    priority_values,
    responded_values,
    start_values,
    status_values,
    target_for,
    update_values,
)
from .display import Clock, current_clock, queue_label, resolution_clock, response_clock

__all__ = [
    "RUNNING_STATUSES",
    "Clock",
    "at_risk_q",
    "breached_q",
    "current_clock",
    "mark_breaches",
    "priority_values",
    "queue_label",
    "resolution_clock",
    "responded_values",
    "response_clock",
    "start_values",
    "status_values",
    "target_for",
    "update_values",
]
