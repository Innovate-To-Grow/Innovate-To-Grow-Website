"""What staff do to tickets, each step recorded in the ticket's audit trail (``TicketEvent``).

Every change is a targeted update of the fields it concerns, so it never overwrites what the ingest wrote meanwhile
(a new participant, the unread mark). Nothing here sends anything: shadow mode (``shadow``) has no sending code.
Merging moves the messages of every selected ticket to the oldest one and marks the others merged (nothing is
deleted); marking spam closes a ticket as spam; "move to the queue" turns an automated ticket into a normal open one
when the classifier was wrong.
"""

from django.db import transaction
from django.utils import timezone

from apps.core.services.email.inbound import scrub_links
from apps.core.utils.access import user_can_access_app

from ..models import Ticket, TicketEvent, TicketMessage
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
    """Apply staff's changes to status, priority, category and assignee; the names of the fields that changed."""
    now = timezone.now()
    values, changed = {}, []
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if "status" in changes and changes["status"] != current.status:
            values.update(_status_values(current, changes["status"], now))
            events.record(current, Kind.STATUS, actor=actor, **{"from": current.status, "to": changes["status"]})
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
            body_text=scrub_links(body.strip())[:NOTE_MAX_CHARS],
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
        update_ticket(ticket, actor=actor, status=Status.SPAM)
        events.record(ticket, Kind.SPAM, actor=actor)
        count += 1
    return count


def move_to_queue(tickets, *, actor) -> int:
    """Automated (or spam) tickets the classifier got wrong become normal open, unread tickets."""
    now = timezone.now()
    count = 0
    for ticket in tickets:
        if not ticket.automated and ticket.status != Status.SPAM:
            continue
        with transaction.atomic():
            Ticket.objects.filter(pk=ticket.pk).update(
                automated=False, status=Status.OPEN, closed_at=None, resolved_at=None, unread=True, updated_at=now
            )
            events.record(ticket, Kind.RECLASSIFIED, actor=actor, **{"from": ticket.classification, "to": "human"})
        count += 1
    return count


def merge(tickets, *, actor) -> Ticket | None:
    """Merge every ticket into the oldest (lowest number); returns it, or None with fewer than two tickets."""
    tickets = sorted({ticket.pk: ticket for ticket in tickets if ticket.status != Status.MERGED}.values(), key=_number)
    if len(tickets) < 2:
        return None
    target, sources = tickets[0], tickets[1:]
    now = timezone.now()
    with transaction.atomic():
        target = Ticket.objects.select_for_update().get(pk=target.pk)
        participants = list(target.participants)
        last_activity = target.last_activity_at
        for source in sources:
            source = Ticket.objects.select_for_update().get(pk=source.pk)
            moved = TicketMessage.objects.filter(ticket=source).update(ticket=target, updated_at=now)
            participants += [*source.participants, source.requester_email]
            last_activity = max(last_activity, source.last_activity_at)
            Ticket.objects.filter(pk=source.pk).update(
                status=Status.MERGED, merged_into=target, closed_at=source.closed_at or now, updated_at=now
            )
            events.record(source, Kind.MERGED, actor=actor, into=target.number)
            events.record(target, Kind.MERGED, actor=actor, source=source.number, messages=moved)
        unique = [address for address in dict.fromkeys(participants) if address]
        Ticket.objects.filter(pk=target.pk).update(participants=unique, last_activity_at=last_activity, updated_at=now)
    return target


def _number(ticket: Ticket) -> int:
    return ticket.number
