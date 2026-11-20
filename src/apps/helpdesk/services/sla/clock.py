"""A ticket's SLA clock: a response and a resolution due time from its priority's ``SLATarget`` (calendar time).

- The clock starts when the ticket's first message arrived (``sla_started_at``). Automated mail, backfilled mail and
  tickets from before the SLA existed have no clock. A ticket whose priority's target is switched off has a start but
  no due times, until a change to a priority with an active target sets them.
- **Response** is met by the first of: a reply from the ticket reaching the mail service (when it is sent, not when it
  is queued: a reply that fails is no response), or staff moving the ticket out of New (``first_responded_at``). The
  site cannot see answers written in Outlook; moving the ticket on stands for them.
- **Resolution** runs while the ticket is New, In progress or On hold – awaiting internal, and stands still while it
  waits for the requester and while it is resolved or closed (``sla_paused_at``). When it runs again, the time it
  stood still is added to the due time (``sla_paused_seconds``), so a reply that reopens a resolved ticket continues
  the clock where it stopped.
- A clock is **breached** once its due time passes before it is met; the flag stays (the worker's maintenance sets it
  for clocks still running, ``breaches.mark_breaches``) unless a priority change sets new targets, which judges both
  again. How a clock reads (on track, at risk, …) is ``display``.

Every function returns the column values to write, for the caller's own targeted update under its row lock.
"""

from datetime import datetime, timedelta

from ...models import SLATarget, Ticket

Status = Ticket.Status
# The resolution clock runs in these statuses (and stands still in every other one).
RUNNING_STATUSES = (Status.NEW, Status.OPEN, Status.PENDING_INTERNAL)


def target_for(priority: str) -> SLATarget | None:
    return SLATarget.objects.filter(priority=priority, is_active=True).first()


def start_values(priority: str, started_at: datetime) -> dict:
    """The clock of a new ticket of ``priority`` whose first message arrived at ``started_at``. A priority whose target
    is switched off gets the start without due times: a later change to a priority with an active target sets them."""
    target = target_for(priority)
    if target is None:
        return {"sla_started_at": started_at}
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


def update_values(
    current: Ticket, values: dict, status: str | None, now: datetime, *, respond: bool = True
) -> tuple[dict, bool]:
    """The clock's columns for ``update_ticket``'s changes (``values``, and a move to ``status`` when not None), and
    whether this is the first response: staff moving a ticket on while it has none yet (out of New, typically, or
    back from a reply that did not go out); not with ``respond`` False (a reply's own status change, whose sending is
    the response, or the system's own moves), nor a move to spam. Both are judged on the row as it will be once a
    priority change in the same save applies its new due times."""
    result, responded = {}, False
    if "priority" in values:
        result.update(priority_values(current, values["priority"], now))
    if status is None:
        return result, responded
    staged = Ticket(**{**_clock(current), **{key: value for key, value in result.items() if key in CLOCK_FIELDS}})
    staged.status = current.status
    # Without a clock (tickets from before the SLA, automated mail) only leaving New counts, as it always did.
    unanswered = current.first_responded_at is None and (current.status == Status.NEW or current.sla_started_at)
    if respond and unanswered and status != Status.SPAM:
        first = responded_values(staged, now)
        if first:
            result.update(first)
            responded = True
    result.update(status_values(staged, status, now))
    return result, responded


CLOCK_FIELDS = (
    "sla_started_at",
    "response_due_at",
    "resolution_due_at",
    "first_responded_at",
    "sla_paused_at",
    "sla_paused_seconds",
    "response_breached",
    "resolution_breached",
)


def _clock(ticket: Ticket) -> dict:
    return {field: getattr(ticket, field) for field in CLOCK_FIELDS}
