"""The helpdesk's scheduled ticket work (the worker's hourly maintenance, "Helpdesk SLA and auto-close").

- Resolved tickets close by themselves ``auto_close_resolved_days`` after they were resolved (0: never), as in
  ServiceNow: a requester's reply before then reopens the ticket (the ingest's reopen rule). The change is made by
  the system (no actor) and is on the ticket's timeline.
- SLA clocks still running past their due time are flagged as breached (``breaches.mark_breaches``).
"""

from datetime import timedelta

from django.utils import timezone

from ...models import HelpdeskSettings, Ticket
from ..tickets.changes import update_ticket
from .breaches import mark_breaches

AUTO_CLOSE_BATCH = 500


def auto_close_resolved(*, now=None, should_stop=None) -> int:
    settings = HelpdeskSettings.load()
    days = int(settings.auto_close_resolved_days)
    if days <= 0:
        return 0
    now = now or timezone.now()
    due = Ticket.objects.filter(status=Ticket.Status.RESOLVED, resolved_at__lt=now - timedelta(days=days))
    closed = 0
    for ticket in list(due.order_by("resolved_at")[:AUTO_CLOSE_BATCH]):
        if should_stop is not None and should_stop():
            break
        # ``update_ticket`` locks and judges the row again: a ticket reopened meanwhile is left alone.
        fresh = Ticket.objects.filter(pk=ticket.pk, status=Ticket.Status.RESOLVED).first()
        reason = f"closed automatically {days} day{'s' if days != 1 else ''} after it was resolved"
        if fresh is not None and "status" in update_ticket(
            fresh, actor=None, status=Ticket.Status.CLOSED, reason=reason
        ):
            closed += 1
    return closed


def run(*, should_stop=None) -> dict[str, int]:
    return {
        "auto_closed": auto_close_resolved(should_stop=should_stop),
        "sla_breaches": mark_breaches(should_stop=should_stop),
    }
