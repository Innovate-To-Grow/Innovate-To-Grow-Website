"""What staff change on a ticket's fields (``update_ticket``), and the rules every change path shares: the assignee is
a member of the assignment group (``membership_problem``), and reopening clears the resolution."""

from django.db import transaction
from django.utils import timezone

from apps.core.utils.access import user_can_access_app

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
    "assignment_group",
    "assignee",
    "resolution_code",
    "resolution_notes",
)
RESOLUTION_NOTES_MAX_CHARS = 20000


class AssignmentRefused(ValueError):
    """The assignee is not a member of the ticket's assignment group (the message says so)."""


def _name(member) -> str:
    if member is None:
        return ""
    return member.get_full_name() or str(member)


def helpdesk_staff():
    """Active staff who may work tickets (the Helpdesk grant, or I2G Master), for the assignee choices."""
    from apps.authn.models import Member

    members = Member.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
    return [member for member in members if user_can_access_app(member, "helpdesk")]


def membership_problem(group, assignee) -> str:
    """Why ``assignee`` cannot hold a ticket of ``group`` ("" when they can): a group that has members has its
    tickets assigned within them."""
    if group is None or assignee is None:
        return ""
    members = group.members.all()
    if members.exists() and not members.filter(pk=assignee.pk).exists():
        return f"{assignee} is not a member of {group}."
    return ""


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
    for field in ("impact", "urgency", "category", "assignment_group", "assignee", "resolution_code"):
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
    category = values.get("category")
    if category is not None and not current.assignment_group_id and "assignment_group" not in values:
        # The category's assignment rule routes a ticket that has no group yet, to an active group its assignee
        # (if any) belongs to.
        default = category.default_group
        if default is not None and default.is_active:
            if not membership_problem(default, values.get("assignee", current.assignee)):
                values["assignment_group"] = default
    return values


def update_ticket(ticket: Ticket, *, actor, first_response: bool = True, reason: str = "", **changes) -> list[str]:
    """Apply staff's changes (``FIELDS``); the names of the fields that changed, in ``FIELDS`` order.

    Impact and urgency set the priority (``sla.priority``); a priority given directly (the services' own callers) is
    kept as given. A category with a default group assigns that group to a ticket without one. An assignee outside
    the ticket's group raises ``AssignmentRefused`` before anything changes. The SLA clock follows: a new priority sets
    new due times, leaving New is the first response (unless ``first_response`` is False: a reply's own status change
    waits for the reply to be sent), and a move into or out of a waiting status stops or starts the resolution clock
    (``sla``); a breach a change brings to light is recorded. Reopening clears the resolution. Assigning someone else
    (or a group with nobody in it) notifies them when sending is on (``outbound.notifications``).

    A merge is final, and only ``merge`` makes one: a merged ticket keeps its status, and no ticket is set to merged
    here. Either change would leave ``merged_into`` out of step with the status. It is ignored.
    """
    now = timezone.now()
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        values = _field_values(current, changes)
        if {"assignment_group", "assignee"} & set(values):
            group = values.get("assignment_group", current.assignment_group)
            problem = membership_problem(group, values.get("assignee", current.assignee))
            if problem:
                raise AssignmentRefused(problem)
        status = changes.get("status", current.status)
        status_changed = status != current.status and Status.MERGED not in (status, current.status)
        if status_changed:
            data = {"from": current.status, "to": status, **({"reason": reason} if reason else {})}
            events.record(current, Kind.STATUS, actor=actor, **data)
            values.update(reopen_values(current, status))
        events.record_changes(current, values, actor=actor, name=_name)
        if status_changed:
            values.update(_status_values(current, status, now))
        clock_status = status if status_changed else None
        sla_values, responded = sla.update_values(current, values, clock_status, now, respond=first_response)
        if responded:
            events.record(current, Kind.RESPONDED, actor=actor, by="status")
        for which in ("response", "resolution"):
            if sla_values.get(f"{which}_breached") and not getattr(current, f"{which}_breached"):
                events.record(current, Kind.SLA_BREACHED, which=which)
        changed = [field for field in FIELDS if field in values]
        if values or sla_values:
            Ticket.objects.filter(pk=current.pk).update(**values, **sla_values, updated_at=now)
        if "assignee" in values or "assignment_group" in values:
            from ..outbound import notifications

            notifications.assignment_changed(
                current,
                actor=actor,
                assignee_changed="assignee" in values,
                group_changed="assignment_group" in values,
            )
    return changed
