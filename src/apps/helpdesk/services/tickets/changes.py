"""What staff change on a ticket: status, assignee, notes, read state, spam, and moving it back to the queue."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.email.inbound import scrub_links
from apps.core.utils.access import user_can_access_app

from ...models import Ticket, TicketEvent, TicketMessage
from . import events

Status = Ticket.Status
Kind = TicketEvent.Kind
NOTE_MAX_CHARS = 20000


def _name(member) -> str:
    if member is None:
        return ""
    return member.get_full_name() or str(member)


def helpdesk_staff():
    """Active staff who may work tickets (the Helpdesk grant, or I2G Master), for the assignee choices."""
    from apps.authn.models import Member

    members = Member.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
    return [member for member in members if user_can_access_app(member, "helpdesk")]


def _status_values(ticket: Ticket, status: str, now) -> dict:
    values = {"status": status}
    if status in Ticket.CLOSED_STATUSES:
        values["closed_at"] = ticket.closed_at or now
        if status == Status.RESOLVED:
            values["resolved_at"] = ticket.resolved_at or now
    else:
        values.update(closed_at=None, resolved_at=None)
    return values


def update_ticket(ticket: Ticket, *, actor, **changes) -> list[str]:
    """Apply staff's changes to status, priority, category and assignee; the names of the fields that changed.

    A merge is final, and only ``merge`` makes one: a merged ticket keeps its status, and no ticket is set to merged
    here. Either change would leave ``merged_into`` out of step with the status: an empty ticket back in the queue
    whose mail still goes to the ticket it was merged into, or a ticket "merged" into nothing. It is ignored.
    """
    now = timezone.now()
    values, changed = {}, []
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        status = changes.get("status", current.status)
        if status != current.status and Status.MERGED not in (status, current.status):
            values.update(_status_values(current, status, now))
            events.record(current, Kind.STATUS, actor=actor, **{"from": current.status, "to": status})
        if "priority" in changes and changes["priority"] != current.priority:
            values["priority"] = changes["priority"]
            events.record(current, Kind.PRIORITY, actor=actor, **{"from": current.priority, "to": changes["priority"]})
        if "category" in changes and changes["category"] != current.category:
            values["category"] = changes["category"]
            labels = {"from": str(current.category or ""), "to": str(changes["category"] or "")}
            events.record(current, Kind.CATEGORY, actor=actor, **labels)
        if "assignee" in changes and changes["assignee"] != current.assignee:
            values["assignee"] = changes["assignee"]
            labels = {"from": _name(current.assignee), "to": _name(changes["assignee"])}
            events.record(current, Kind.ASSIGNED, actor=actor, **labels)
        if values:
            changed = [key for key in ("status", "priority", "category", "assignee") if key in values]
            Ticket.objects.filter(pk=current.pk).update(**values, updated_at=now)
    return changed


def add_note(ticket: Ticket, *, actor, body: str) -> TicketMessage:
    """An internal note (never sent; personal sign-in links pasted into it are scrubbed like inbound mail)."""
    now = timezone.now()
    with transaction.atomic():
        note = TicketMessage.objects.create(
            ticket=ticket,
            kind=TicketMessage.Kind.NOTE,
            author=actor,
            from_name=_name(actor)[:255],
            occurred_at=now,
            # NUL cannot be stored in PostgreSQL text; a pasted one is dropped rather than failing the save.
            body_text=scrub_links(body.replace("\x00", "").strip())[:NOTE_MAX_CHARS],
        )
        events.record(ticket, Kind.NOTE, actor=actor)
        Ticket.objects.filter(pk=ticket.pk).update(last_activity_at=now, updated_at=now)
    return note


def mark_read(tickets) -> int:
    return Ticket.objects.filter(pk__in=[ticket.pk for ticket in tickets], unread=True).update(unread=False)


def set_status(tickets, status: str, *, actor) -> int:
    return sum(1 for ticket in tickets if update_ticket(ticket, actor=actor, status=status))


def assign(tickets, assignee, *, actor) -> int:
    return sum(1 for ticket in tickets if update_ticket(ticket, actor=actor, assignee=assignee))


def mark_spam(tickets, *, actor) -> int:
    count = 0
    for ticket in tickets:
        if ticket.status in (Status.SPAM, Status.MERGED):
            continue
        # ``update_ticket`` judges the locked row again: a ticket merged (or marked spam) meanwhile is left alone.
        if "status" in update_ticket(ticket, actor=actor, status=Status.SPAM):
            events.record(ticket, Kind.SPAM, actor=actor)
            count += 1
    return count


def move_to_queue(tickets, *, actor) -> int:
    """Automated (or spam) tickets the classifier got wrong become normal open, unread tickets. A merged one stays as
    it is: its messages are on the ticket it was merged into, so it would only be an empty ticket in the queue. The
    update checks the row itself, so a ticket merged (or moved) since the list was shown is left alone."""
    now = timezone.now()
    count = 0
    for ticket in tickets:
        if not ticket.is_automated_or_spam or ticket.status == Status.MERGED:
            continue
        with transaction.atomic():
            moved = (
                Ticket.objects.filter(Q(automated=True) | Q(status=Status.SPAM), pk=ticket.pk)
                .exclude(status=Status.MERGED)
                .update(
                    automated=False, status=Status.OPEN, closed_at=None, resolved_at=None, unread=True, updated_at=now
                )
            )
            if moved:
                events.record(ticket, Kind.RECLASSIFIED, actor=actor, **{"from": ticket.classification, "to": "human"})
        count += moved
    return count
