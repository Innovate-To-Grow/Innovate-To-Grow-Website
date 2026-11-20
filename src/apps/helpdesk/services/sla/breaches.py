"""Which tickets' SLA is breached or at risk (the queue's SLA filter and view), and the worker's marking of clocks
that ran past their due time."""

import operator
from datetime import datetime, timedelta
from functools import reduce

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ...models import SLATarget, Ticket, TicketEvent
from .clock import RUNNING_STATUSES


def _response_overdue(now: datetime) -> Q:
    return Q(first_responded_at__isnull=True, response_due_at__lt=now, status__in=Ticket.OPEN_STATUSES)


def _resolution_overdue(now: datetime) -> Q:
    return Q(sla_paused_at__isnull=True, resolution_due_at__lt=now, status__in=RUNNING_STATUSES)


def breached_q(now: datetime) -> Q:
    """Tickets whose response or resolution is breached (flagged, or overdue and not flagged yet)."""
    return Q(response_breached=True) | Q(resolution_breached=True) | _response_overdue(now) | _resolution_overdue(now)


def at_risk_q(now: datetime, warning_percent: int) -> Q:
    """Open tickets with a clock running past ``warning_percent`` of its target and not overdue yet: what the queue's
    SLA column shows as at risk. A clock's due time is its start plus the target (plus the time it stood still), so
    "past the share" is "due within the rest of the target" for the ticket's priority."""
    rest = (100 - int(warning_percent)) / 100
    parts = []
    for target in SLATarget.objects.all():
        response_until = now + timedelta(minutes=target.response_minutes * rest)
        resolution_until = now + timedelta(minutes=target.resolution_minutes * rest)
        response = Q(first_responded_at__isnull=True, response_due_at__gte=now, response_due_at__lte=response_until)
        resolution = Q(sla_paused_at__isnull=True, resolution_due_at__gte=now, resolution_due_at__lte=resolution_until)
        parts.append(
            Q(priority=target.priority)
            & ((response & Q(status__in=Ticket.OPEN_STATUSES)) | (resolution & Q(status__in=RUNNING_STATUSES)))
        )
    return reduce(operator.or_, parts) if parts else Q(pk__in=[])


def mark_breaches(*, now: datetime | None = None, should_stop=None) -> int:
    """Flag the running clocks whose due time passed (each one once, with an "SLA breached" entry); how many."""
    now = now or timezone.now()
    flagged = 0
    for field, overdue, what in (
        ("response_breached", _response_overdue(now), "response"),
        ("resolution_breached", _resolution_overdue(now), "resolution"),
    ):
        ids = list(Ticket.objects.filter(overdue, **{field: False}).values_list("pk", flat=True)[:500])
        for pk in ids:
            if should_stop is not None and should_stop():
                return flagged
            with transaction.atomic():
                # The update judges the row again, so a ticket answered or resolved meanwhile is not flagged.
                if Ticket.objects.filter(overdue, pk=pk, **{field: False}).update(**{field: True}):
                    TicketEvent.objects.create(ticket_id=pk, kind=TicketEvent.Kind.SLA_BREACHED, data={"which": what})
                    flagged += 1
    return flagged
