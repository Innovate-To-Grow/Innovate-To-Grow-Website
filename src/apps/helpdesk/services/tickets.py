"""What staff do to tickets, each step recorded in the ticket's audit trail (``TicketEvent``).

Every change is a targeted update of the fields it concerns, so it never overwrites what the ingest wrote meanwhile
(a new participant, the unread mark). Nothing here sends anything: shadow mode (``shadow``) has no sending code.
Merging moves the messages of every selected ticket to the oldest one and marks the others merged (nothing is
deleted); marking spam closes a ticket as spam; "move to the queue" turns an automated ticket into a normal open one
when the classifier was wrong.

A merge never goes into automated mail or spam (Hongzhe's decision of 2026-11-12: people's messages would be hidden
in it), and spam is never merged at all: ``merge`` raises ``MergeRefused`` before it changes anything. Automated mail
merged into a person's ticket changes nothing on it but its timeline, like automated mail that threads there by
itself (``ingest.store``), and stays hidden: still automated, now merged. A merge is final: no status change, spam
mark or move to the queue un-merges a ticket, and only ``merge`` makes one merged.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.email.inbound import LABELS, scrub_links
from apps.core.utils.access import user_can_access_app

from ..models import Ticket, TicketEvent, TicketMessage
from . import events

Status = Ticket.Status
Kind = TicketEvent.Kind
NOTE_MAX_CHARS = 20000
# The admin action that turns misclassified mail into a normal ticket, named in the merge refusals.
MOVE_TO_QUEUE = "Not automated: move to the queue"


class MergeRefused(Exception):
    """A merge refused before anything changed; the message tells staff why and what to do instead."""


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


def _planned(tickets) -> list[Ticket]:
    """The tickets a merge takes, each once and none merged already, oldest (the target) first."""
    unique = {ticket.pk: ticket for ticket in tickets if ticket.status != Status.MERGED}
    return sorted(unique.values(), key=_number)


def _is_spam(ticket: Ticket) -> bool:
    return ticket.status == Status.SPAM or (ticket.automated and ticket.classification == "spam")


def _hidden_kind(ticket: Ticket) -> str:
    """What an automated or spam ticket is, for staff: spam, or automated mail with the classifier's label."""
    if _is_spam(ticket):
        return "spam"
    label = LABELS.get(ticket.classification)
    return f"automated mail ({label})" if label else "automated mail"


def _refusal(target: Ticket, sources) -> str:
    """Why these tickets cannot be merged into ``target`` ("" when they can)."""
    if target.is_automated_or_spam:
        return (
            f"Nothing was merged: {target.display_number}, the oldest selected ticket, is {_hidden_kind(target)}, "
            "and nothing is merged into automated mail or spam. Leave it out of the selection, or use "
            f'"{MOVE_TO_QUEUE}" on it first if a person wrote it.'
        )
    spam = next((source for source in sources if _is_spam(source)), None)
    if spam is not None:
        return (
            f"Nothing was merged: {spam.display_number} is spam, and spam is never merged into a person's ticket. "
            f'Leave it out of the selection, or use "{MOVE_TO_QUEUE}" on it first if it is not spam.'
        )
    merged = next((ticket for ticket in (target, *sources) if ticket.status == Status.MERGED), None)
    if merged is not None:
        return f"Nothing was merged: {merged.display_number} was merged meanwhile. Reload the list and try again."
    return ""


def merge_refusal(tickets) -> str:
    """Why ``merge`` would refuse these tickets, asked before anything is locked ("" when it would not; fewer than two
    is not a refusal: ``merge`` returns None). The admin asks it before the typed confirmation."""
    planned = _planned(tickets)
    return _refusal(planned[0], planned[1:]) if len(planned) > 1 else ""


def merge(tickets, *, actor) -> Ticket | None:
    """Merge every ticket into the oldest (lowest number); returns it, or None with fewer than two tickets.

    Raises ``MergeRefused`` before anything changes when the oldest is automated mail or spam, when another one is
    spam, or when one was merged meanwhile; the rows are judged once locked, so a ticket marked spam since the list
    was shown is caught too. Automated mail moves its messages (still collapsed automated entries) and nothing else:
    the ticket's status, unread mark, participants and last activity stay as they were.
    """
    planned = _planned(tickets)
    if len(planned) < 2:
        return None
    now = timezone.now()
    with transaction.atomic():
        # Oldest first, the order every merge locks in.
        target, *sources = [Ticket.objects.select_for_update().get(pk=ticket.pk) for ticket in planned]
        refusal = _refusal(target, sources)
        if refusal:
            raise MergeRefused(refusal)
        participants = list(target.participants)
        last_activity = target.last_activity_at
        for source in sources:
            moved = TicketMessage.objects.filter(ticket=source).update(ticket=target, updated_at=now)
            if not source.automated:
                # Automated mail's addresses would let its senders (and anyone it was sent to) thread into the
                # person's ticket by its number or conversation; its time would move the ticket up the queue.
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
