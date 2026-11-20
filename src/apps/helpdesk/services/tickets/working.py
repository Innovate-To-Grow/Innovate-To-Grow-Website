"""What staff do to tickets in bulk or beside the ticket form: notes, the read mark, resolving and closing, reopening,
assigning, marking spam, and moving misclassified mail back to the queue. Each step goes through ``update_ticket``
(or a targeted update of its own columns), so the audit trail and the SLA clock follow every path alike."""

import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.email.inbound import LINK_PLACEHOLDER, is_sensitive_url

from ...models import Ticket, TicketMessage
from .. import sla
from ..sla.priority import AUTOMATED_DEFAULT, PERSON_DEFAULT, priority_for
from . import events
from .changes import DONE, AssignmentRefused, Kind, Status, _name, update_ticket

NOTE_MAX_CHARS = 20000
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s\"'<>]+")


def scrub_sign_in_links(value) -> str:
    """Text staff write (a note, a reply) with only the site's personal sign-in and subscription links replaced: every
    other link is kept as written, long ones included."""
    return _URL_RE.sub(lambda match: LINK_PLACEHOLDER if is_sensitive_url(match.group(0)) else match.group(0), value)


def add_note(ticket: Ticket, *, actor, body: str) -> TicketMessage:
    """An internal note (never sent; a personal sign-in link pasted into it is removed)."""
    now = timezone.now()
    with transaction.atomic():
        note = TicketMessage.objects.create(
            ticket=ticket,
            kind=TicketMessage.Kind.NOTE,
            author=actor,
            from_name=_name(actor)[:255],
            occurred_at=now,
            # NUL cannot be stored in PostgreSQL text; a pasted one is dropped rather than failing the save.
            body_text=scrub_sign_in_links(body.replace("\x00", "").replace("\r\n", "\n").strip())[:NOTE_MAX_CHARS],
        )
        events.record(ticket, Kind.NOTE, actor=actor)
        Ticket.objects.filter(pk=ticket.pk).update(last_activity_at=now, updated_at=now)
    return note


def mark_read(tickets) -> int:
    return Ticket.objects.filter(pk__in=[ticket.pk for ticket in tickets], unread=True).update(unread=False)


def mark_unread(tickets) -> int:
    return Ticket.objects.filter(pk__in=[ticket.pk for ticket in tickets], unread=False).update(unread=True)


def _person_ticket(ticket: Ticket) -> bool:
    return not ticket.is_automated_or_spam and ticket.status != Status.MERGED


def set_status(tickets, status: str, *, actor, **values) -> int:
    """``status`` (with ``values``, e.g. a resolution code) on each ticket; how many changed."""
    return sum(1 for ticket in tickets if "status" in update_ticket(ticket, actor=actor, status=status, **values))


def resolve(tickets, *, actor, code: str, notes: str = "") -> int:
    """Resolve people's open tickets with a resolution code (and notes); the others are left as they are."""
    chosen = [ticket for ticket in tickets if _person_ticket(ticket) and ticket.is_open]
    return set_status(chosen, Status.RESOLVED, actor=actor, resolution_code=code, resolution_notes=notes)


def close(tickets, *, actor) -> int:
    """Close resolved people's tickets (they carry their resolution code); the others are left as they are."""
    chosen = [ticket for ticket in tickets if _person_ticket(ticket) and ticket.status == Status.RESOLVED]
    return set_status(chosen, Status.CLOSED, actor=actor)


def reopen(tickets, *, actor) -> int:
    """Reopen resolved or closed people's tickets (In progress; the resolution is cleared). Automated mail and spam
    go back with "Not automated: move to the queue", a merged ticket never."""
    chosen = [ticket for ticket in tickets if _person_ticket(ticket) and ticket.status in DONE]
    return set_status(chosen, Status.OPEN, actor=actor)


def assign(tickets, assignee, *, actor) -> tuple[int, int]:
    """Assign (or with None unassign) each ticket; (how many changed, how many were refused because ``assignee`` is
    not a member of the ticket's assignment group)."""
    changed = refused = 0
    for ticket in tickets:
        try:
            changed += bool(update_ticket(ticket, actor=actor, assignee=assignee))
        except AssignmentRefused:
            refused += 1
    return changed, refused


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
    """Automated (or spam) tickets the classifier or staff got wrong become people's open, unread tickets, with an SLA
    clock running: New again when nobody answered it yet (so moving it on is still its first response), else In
    progress. A merged one stays as it is: its messages are on the ticket it was merged into. The update checks the
    row itself, so a ticket merged (or moved) since the list was shown is left alone."""
    now = timezone.now()
    count = 0
    for ticket in tickets:
        if not ticket.is_automated_or_spam or ticket.status == Status.MERGED:
            continue
        with transaction.atomic():
            current = Ticket.objects.select_for_update().get(pk=ticket.pk)
            if not current.is_automated_or_spam or current.status == Status.MERGED:
                continue
            status = Status.NEW if current.first_responded_at is None else Status.OPEN
            values = {"automated": False, "status": status, "closed_at": None, "resolved_at": None, "unread": True}
            if current.automated and (current.impact, current.urgency) == AUTOMATED_DEFAULT:
                # Automated mail starts low; a person's message starts where any other does (a person's ticket staff
                # marked spam keeps the impact and urgency staff gave it).
                impact, urgency = PERSON_DEFAULT
                reset = {"impact": impact, "urgency": urgency}
                if priority_for(impact, urgency) != current.priority:
                    reset["priority"] = priority_for(impact, urgency)
                events.record_changes(current, reset, actor=actor, name=_name)
                values.update(reset)
            if current.sla_started_at is None:
                # Automated mail never had a clock: it starts now, the moment it became a person's request.
                values.update(sla.start_values(values.get("priority", current.priority), now))
            else:
                values.update(sla.status_values(current, status, now))
            Ticket.objects.filter(Q(automated=True) | Q(status=Status.SPAM), pk=current.pk).update(
                **values, updated_at=now
            )
            events.record(current, Kind.RECLASSIFIED, actor=actor, **{"from": current.classification, "to": "human"})
        count += 1
    return count
