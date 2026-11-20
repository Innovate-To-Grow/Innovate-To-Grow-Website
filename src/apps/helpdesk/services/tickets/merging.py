"""Merging tickets: what may be merged into what (and why not), and the merge itself."""

from django.db import transaction
from django.utils import timezone

from apps.core.services.email.inbound import LABELS

from ...models import Ticket, TicketMessage
from . import events
from .changes import Kind, Status

MOVE_TO_QUEUE = "Not automated: move to the queue"


class MergeRefused(Exception):
    """A merge refused before anything changed; the message tells staff why and what to do instead."""


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
    the ticket's status, unread mark, participants and last activity stay as they were. A person's ticket brings its
    unread mark, and when it was still open and the oldest is resolved or closed, the oldest is reopened (its SLA
    clock runs again), so the request stays in the queue. A reply still waiting to be sent is not sent: it was
    written for the ticket it was on, and is marked so on the timeline.
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
        last_activity, unread, still_open = target.last_activity_at, target.unread, False
        for source in sources:
            _stop_queued_replies(source, target)
            moved = TicketMessage.objects.filter(ticket=source).update(ticket=target, updated_at=now)
            if not source.automated:
                # Automated mail's addresses would let its senders (and anyone it was sent to) thread into the
                # person's ticket by its number or conversation; its time would move the ticket up the queue.
                participants += [*source.participants, source.requester_email]
                last_activity = max(last_activity, source.last_activity_at)
                unread = unread or source.unread
                still_open = still_open or source.is_open
            Ticket.objects.filter(pk=source.pk).update(
                status=Status.MERGED, merged_into=target, closed_at=source.closed_at or now, updated_at=now
            )
            events.record(source, Kind.MERGED, actor=actor, into=target.number)
            events.record(target, Kind.MERGED, actor=actor, source=source.number, messages=moved)
        unique = [address for address in dict.fromkeys(participants) if address]
        Ticket.objects.filter(pk=target.pk).update(
            participants=unique, last_activity_at=last_activity, unread=unread, updated_at=now
        )
        if still_open and target.status in (Status.RESOLVED, Status.CLOSED):
            from .changes import update_ticket

            update_ticket(target, actor=actor, status=Status.OPEN, reason="an open ticket was merged into it")
    return target


def _stop_queued_replies(source: Ticket, target: Ticket) -> None:
    """Replies queued on ``source`` are not sent once it is merged (the send job sends only queued replies)."""
    error = (
        f"Not sent: {source.display_number} was merged into {target.display_number} before it went out. "
        "Write the reply again here if it is still needed."
    )
    queued = TicketMessage.objects.filter(
        ticket=source, kind=TicketMessage.Kind.REPLY, delivery_status=TicketMessage.Delivery.QUEUED
    )
    for reply in queued:
        TicketMessage.objects.filter(pk=reply.pk).update(
            delivery_status=TicketMessage.Delivery.FAILED, delivery_error=error
        )
        what = "acknowledgement" if reply.automatic else "reply"
        events.record(target, Kind.REPLY_FAILED, what=what, error=error)


def _number(ticket: Ticket) -> int:
    return ticket.number
