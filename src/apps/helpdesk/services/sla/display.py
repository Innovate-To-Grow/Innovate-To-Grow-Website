"""How an SLA clock reads on the ticket page and in the queue: none, on track, at risk, paused, breached or met."""

from dataclasses import dataclass
from datetime import datetime

from ...models import Ticket
from .clock import Status


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
