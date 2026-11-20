"""A ticket's SLA clock: a response and a resolution due time from its priority's ``SLATarget`` (calendar time).

- The clock starts when the ticket's first message arrived (``sla_started_at``). Automated mail, backfilled mail,
  tickets from before the SLA existed and priorities whose target is switched off have no clock (no due times).
- **Response** is met by the first of: a reply sent to the requester from the ticket, or staff moving the ticket out
  of New (``first_responded_at``). The site cannot see answers written in Outlook; moving the ticket on stands for
  them.
- **Resolution** runs while the ticket is New, In progress or On hold – awaiting internal, and stands still while it
  waits for the requester and while it is resolved or closed (``sla_paused_at``). When it runs again, the time it
  stood still is added to the due time (``sla_paused_seconds``), so a reply that reopens a resolved ticket continues
  the clock where it stopped.
- A clock is **breached** once its due time passes before it is met; the flag stays (the worker's maintenance sets it
  for clocks still running, ``mark_breaches``) unless a priority change sets new targets, which judges both again.

Every function returns the column values to write, for the caller's own targeted update under its row lock.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ...models import SLATarget, Ticket, TicketEvent

Status = Ticket.Status
# The resolution clock runs in these statuses (and stands still in every other one).
RUNNING_STATUSES = (Status.NEW, Status.OPEN, Status.PENDING_INTERNAL)


def target_for(priority: str) -> SLATarget | None:
    return SLATarget.objects.filter(priority=priority, is_active=True).first()


def start_values(priority: str, started_at: datetime) -> dict:
    """The clock of a new ticket of ``priority`` whose first message arrived at ``started_at`` (empty: no SLA)."""
    target = target_for(priority)
    if target is None:
        return {}
    return {
        "sla_started_at": started_at,
        "response_due_at": started_at + timedelta(minutes=target.response_minutes),
        "resolution_due_at": started_at + timedelta(minutes=target.resolution_minutes),
    }


def priority_values(ticket: Ticket, priority: str, now: datetime) -> dict:
    """New due times for a priority change (the targets of the new priority, from the same start); both breach flags
    are judged again against them. A ticket without a clock keeps none."""
    if ticket.sla_started_at is None:
        return {}
    target = target_for(priority)
    if target is None:
        return {
            "response_due_at": None,
            "resolution_due_at": None,
            "response_breached": False,
            "resolution_breached": False,
        }
    response_due = ticket.sla_started_at + timedelta(minutes=target.response_minutes)
    # Time it stands still now is added when it starts again (``status_values``), as for any due time.
    resolution_time = timedelta(minutes=target.resolution_minutes, seconds=ticket.sla_paused_seconds)
    resolution_due = ticket.sla_started_at + resolution_time
    return {
        "response_due_at": response_due,
        "resolution_due_at": resolution_due,
        "response_breached": (ticket.first_responded_at or now) > response_due,
        "resolution_breached": (ticket.sla_paused_at or now) > resolution_due,
    }


def responded_values(ticket: Ticket, now: datetime) -> dict:
    """The first response (a reply sent, or staff moving the ticket out of New); nothing once responded."""
    if ticket.first_responded_at is not None:
        return {}
    values = {"first_responded_at": now}
    if ticket.response_due_at is not None and now > ticket.response_due_at:
        values["response_breached"] = True
    return values


def status_values(ticket: Ticket, status: str, now: datetime) -> dict:
    """Stop or start the resolution clock for a move from ``ticket.status`` to ``status``."""
    if ticket.sla_started_at is None or ticket.resolution_due_at is None:
        return {}
    running, will_run = ticket.sla_paused_at is None, status in RUNNING_STATUSES
    if running and not will_run:
        values = {"sla_paused_at": now}
        if now > ticket.resolution_due_at:
            values["resolution_breached"] = True
        return values
    if not running and will_run:
        standing = _standing_seconds(ticket, now)
        return {
            "sla_paused_at": None,
            "sla_paused_seconds": ticket.sla_paused_seconds + standing,
            "resolution_due_at": ticket.resolution_due_at + timedelta(seconds=standing),
        }
    return {}


def _standing_seconds(ticket: Ticket, now: datetime) -> int:
    if ticket.sla_paused_at is None:
        return 0
    return max(0, int((now - ticket.sla_paused_at).total_seconds()))


# --- display ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Clock:
    state: str  # none, running, at_risk, paused, breached, met
    due: datetime | None = None

    @property
    def label(self) -> str:
        return {
            "none": "No SLA",
            "running": "On track",
            "at_risk": "At risk",
            "paused": "Paused",
            "breached": "Breached",
            "met": "Met",
        }[self.state]


def _running_state(start: datetime, due: datetime, paused_seconds: int, now: datetime, warning_percent: int) -> str:
    if now > due:
        return "breached"
    total = (due - start).total_seconds() - paused_seconds
    used = (now - start).total_seconds() - paused_seconds
    return "at_risk" if total > 0 and used >= total * warning_percent / 100 else "running"


def response_clock(ticket: Ticket, now: datetime, warning_percent: int) -> Clock:
    due = ticket.response_due_at
    if due is None or ticket.sla_started_at is None:
        return Clock("none")
    if ticket.first_responded_at is not None:
        return Clock("breached" if ticket.response_breached else "met", due)
    if not ticket.is_open:
        return Clock("breached" if ticket.response_breached else "none", due)
    return Clock(_running_state(ticket.sla_started_at, due, 0, now, warning_percent), due)


def resolution_clock(ticket: Ticket, now: datetime, warning_percent: int) -> Clock:
    due = ticket.resolution_due_at
    if due is None or ticket.sla_started_at is None:
        return Clock("none")
    if ticket.status in (Status.RESOLVED, Status.CLOSED):
        return Clock("breached" if ticket.resolution_breached else "met", due)
    if not ticket.is_open:
        return Clock("none", due)
    if ticket.sla_paused_at is not None:
        return Clock("breached" if ticket.resolution_breached else "paused", due)
    if ticket.resolution_breached:
        return Clock("breached", due)
    state = _running_state(ticket.sla_started_at, due, ticket.sla_paused_seconds, now, warning_percent)
    return Clock(state, due)


def current_clock(ticket: Ticket, now: datetime, warning_percent: int) -> tuple[str, Clock]:
    """The clock the queue shows: the response until it is met, then the resolution."""
    response = response_clock(ticket, now, warning_percent)
    if response.state in ("running", "at_risk", "breached") and ticket.first_responded_at is None and ticket.is_open:
        return "Response", response
    return "Resolution", resolution_clock(ticket, now, warning_percent)


# --- queue filters and the worker's breach marking -------------------------------------------------------------------


def _response_overdue(now: datetime) -> Q:
    return Q(first_responded_at__isnull=True, response_due_at__lt=now, status__in=Ticket.OPEN_STATUSES)


def _resolution_overdue(now: datetime) -> Q:
    return Q(sla_paused_at__isnull=True, resolution_due_at__lt=now, status__in=RUNNING_STATUSES)


def breached_q(now: datetime) -> Q:
    """Tickets whose response or resolution is breached (flagged, or overdue and not flagged yet)."""
    return Q(response_breached=True) | Q(resolution_breached=True) | _response_overdue(now) | _resolution_overdue(now)


def due_soon_q(now: datetime, hours: int = 24) -> Q:
    """Open tickets with a clock running that falls due within ``hours`` (and is not overdue yet)."""
    until = now + timedelta(hours=hours)
    response = Q(first_responded_at__isnull=True, response_due_at__gte=now, response_due_at__lte=until)
    resolution = Q(sla_paused_at__isnull=True, resolution_due_at__gte=now, resolution_due_at__lte=until)
    return (response & Q(status__in=Ticket.OPEN_STATUSES)) | (resolution & Q(status__in=RUNNING_STATUSES))


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
