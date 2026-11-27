"""What staff change on a ticket's fields (``update_ticket``), and the rule every change path shares: reopening clears
the resolution. Tickets have no owner (I2G-HELPDESK-01): every Admin works every ticket, so no change checks who may."""

from django.db import transaction
from django.utils import timezone

from ...models import Ticket, TicketEvent
from .. import sla
from ..sla.priority import priority_for
from . import events

Status = Ticket.Status
Kind = TicketEvent.Kind
DONE = (Status.RESOLVED, Status.CLOSED)
# The editable fields, in the order a change is reported.
FIELDS = (
    "status",
    "impact",
    "urgency",
    "priority",
    "category",
    "resolution_code",
    "resolution_notes",
)
RESOLUTION_NOTES_MAX_CHARS = 20000


def _name(member) -> str:
    if member is None:
        return ""
    return member.get_full_name() or str(member)


def _status_values(ticket: Ticket, status: str, now) -> dict:
    values = {"status": status}
    if status in Ticket.CLOSED_STATUSES:
        values["closed_at"] = ticket.closed_at or now
        if status == Status.RESOLVED:
            values["resolved_at"] = ticket.resolved_at or now
    else:
        values.update(closed_at=None, resolved_at=None)
    return values


def reopen_values(ticket: Ticket, status: str) -> dict:
    """Reopening a resolved or closed ticket clears its resolution: resolving it again asks for a new code."""
    if ticket.status not in DONE or status not in Ticket.OPEN_STATUSES:
        return {}
    return {field: "" for field in ("resolution_code", "resolution_notes") if getattr(ticket, field)}


def _field_values(current: Ticket, changes: dict) -> dict:
    values = {}
    for field in ("impact", "urgency", "category", "resolution_code"):
        if field in changes and changes[field] != getattr(current, field):
            values[field] = changes[field]
    if "resolution_notes" in changes:
        notes = str(changes["resolution_notes"] or "").replace("\x00", "").replace("\r\n", "\n").strip()
        if notes[:RESOLUTION_NOTES_MAX_CHARS] != current.resolution_notes:
            values["resolution_notes"] = notes[:RESOLUTION_NOTES_MAX_CHARS]
    if "impact" in values or "urgency" in values:
        computed = priority_for(values.get("impact", current.impact), values.get("urgency", current.urgency))
        if computed != current.priority:
            values["priority"] = computed
    elif "priority" in changes and changes["priority"] != current.priority:
        values["priority"] = changes["priority"]
    return values


def update_ticket(ticket: Ticket, *, actor, first_response: bool = True, reason: str = "", **changes) -> list[str]:
    """Apply staff's changes (``FIELDS``); the names of the fields that changed, in ``FIELDS`` order.

    Impact and urgency set the priority (``sla.priority``); a priority given directly (the services' own callers) is
    kept as given. Any other keyword (such as the deprecated ``assignee`` or ``assignment_group``) is ignored. The SLA
    clock follows: a new priority sets new due times, leaving New is the first response (unless ``first_response`` is
    False: a reply's own status change waits for the reply to be sent), and a move into or out of a waiting status
    stops or starts the resolution clock (``sla``); a breach a change brings to light is recorded. Reopening clears
    the resolution. Nobody is emailed.

    A merge is final, and only ``merge`` makes one: a merged ticket keeps its status, and no ticket is set to merged
    here. Either change would leave ``merged_into`` out of step with the status. It is ignored.
    """
    now = timezone.now()
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        values = _field_values(current, changes)
        status = changes.get("status", current.status)
        status_changed = status != current.status and Status.MERGED not in (status, current.status)
        if status_changed:
            data = {"from": current.status, "to": status, **({"reason": reason} if reason else {})}
            events.record(current, Kind.STATUS, actor=actor, **data)
            reopened = reopen_values(current, status)
            values.update(reopened)
        events.record_changes(current, values, actor=actor, reopened=bool(status_changed and reopened))
        if status_changed:
            values.update(_status_values(current, status, now))
        clock_status = status if status_changed else None
        sla_values, responded = sla.update_values(current, values, clock_status, now, respond=first_response)
        if responded:
            events.record(current, Kind.RESPONDED, actor=actor, by="status")
        for which in ("response", "resolution"):
            # A breach the change brings to light, or one a new priority's target no longer has (both on record).
            before, after = getattr(current, f"{which}_breached"), sla_values.get(f"{which}_breached")
            if after and not before:
                events.record(current, Kind.SLA_BREACHED, which=which)
            elif after is False and before:
                events.record(current, Kind.SLA_BREACHED, actor=actor, which=which, cleared=True)
        changed = [field for field in FIELDS if field in values]
        if values or sla_values:
            Ticket.objects.filter(pk=current.pk).update(**values, **sla_values, updated_at=now)
    return changed
