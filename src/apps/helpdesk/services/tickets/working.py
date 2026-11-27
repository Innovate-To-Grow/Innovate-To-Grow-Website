"""What staff do to tickets in bulk or beside the ticket form: notes, the read mark, resolving and closing, reopening,
marking spam, and moving misclassified mail back to the queue. Each step goes through ``update_ticket``
(or a targeted update of its own columns), so the audit trail and the SLA clock follow every path alike."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.utils.security import is_plain_address

from ...models import Ticket, TicketMessage
from .. import sla
from ..ingest.routing.people import same_person
from ..sla.priority import AUTOMATED_DEFAULT, PERSON_DEFAULT, priority_for
from . import events
from .changes import DONE, Kind, Status, _name, update_ticket
from .scrub import scrub_sign_in_links

NOTE_MAX_CHARS = 20000
HUMAN = "human"
# Automatic replies of the requester (not their own words): a move leaves them automated.
AUTOMATIC = ("auto_reply", "bounce", "receipt", "system", "own")


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


def _opening(ticket: Ticket) -> TicketMessage | None:
    return ticket.messages.filter(kind__in=TicketMessage.INBOUND_KINDS).order_by("occurred_at", "created_at").first()


def _alias(opening: TicketMessage, name: str) -> bool:
    """Whether the opening message spoke for the sender's other address under their name: never list mail, whose
    sender is the list's address ("Ira Moss via Faculty")."""
    return not opening.list_address and same_person(opening.from_name, name)


def _relayed(ticket: Ticket) -> dict:
    """The requester once ``ticket`` is a person's: whom its opening message spoke for instead of its sender (a web
    form's person, a list's poster, or the sender's other address under their name: judged at intake by
    ``ingest.routing.people``), with the member it belongs to; else nothing to change."""
    opening = _opening(ticket)
    address = str(getattr(opening, "on_behalf_of", "") or "").lower()
    if not address or not is_plain_address(address) or address == ticket.requester_email.lower():
        return {}
    contact = ContactEmail.objects.filter(email_address__iexact=address, member__isnull=False, verified=True).first()
    alias = _alias(opening, opening.on_behalf_name)  # the same person: the member stays theirs
    member = getattr(contact, "member", None) or (ticket.requester_member if alias else None)
    return {"requester_email": address, "requester_name": opening.on_behalf_name, "requester_member": member}


def _theirs(ticket: Ticket, relayed: str) -> bool:
    """The requester's messages filed as automated mail become theirs: shown, quoted under a reply, and warned about
    as suspicious (no longer spam) when the scam checks scored them; whether one was. Their automatic replies (an
    out-of-office, a bounce) stay automated, except the message that opened the ticket: that one was misjudged."""
    opening = _opening(ticket)
    sender = Q(from_address__iexact=ticket.requester_email) | (
        Q(on_behalf_of__iexact=relayed) if relayed else Q(pk=None)
    )
    misjudged = Q(pk=getattr(opening, "pk", None)) | ~Q(classification__in=AUTOMATIC)
    filed = TicketMessage.objects.filter(sender, misjudged, ticket=ticket, kind=TicketMessage.Kind.AUTOMATED)
    scored = filed.filter(scam_level__in=("medium", "high")).exists()
    filed.filter(scam_level="high").update(scam_level="medium")
    filed.update(kind=TicketMessage.Kind.CUSTOMER, classification=HUMAN)
    return scored


def move_to_queue(tickets, *, actor) -> int:
    """Automated (or spam) tickets the classifier or staff got wrong become people's open, unread tickets, with an SLA
    clock running: New again when nobody answered it yet (so moving it on is still its first response), else In
    progress; classified as a person's, with the requester's messages theirs again (``_theirs``). A merged one stays
    as it is: its messages are on the ticket it was merged into. The update checks the row itself, so a ticket merged
    (or moved) since the list was shown is left alone."""
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
            values = {"automated": False, "classification": HUMAN, "status": status, "unread": True}
            values.update(closed_at=None, resolved_at=None)
            relayed = _relayed(current)
            if _theirs(current, relayed.get("requester_email", "")):
                values["flags"] = list(dict.fromkeys([*current.flags, "suspicious"]))
            values.update(relayed)
            if relayed:  # listed as theirs at once, as on a new ticket
                values["participants"] = list(dict.fromkeys([*current.participants, relayed["requester_email"]]))
            if current.automated and (current.impact, current.urgency) == AUTOMATED_DEFAULT:
                # Automated mail starts low; a person's message starts where any other does (a person's ticket staff
                # marked spam keeps the impact and urgency staff gave it).
                impact, urgency = PERSON_DEFAULT
                reset = {"impact": impact, "urgency": urgency}
                if priority_for(impact, urgency) != current.priority:
                    reset["priority"] = priority_for(impact, urgency)
                events.record_changes(current, reset, actor=actor)
                values.update(reset)
            if current.sla_started_at is None:
                # Automated mail never had a clock: it starts now, the moment it became a person's request.
                values.update(sla.start_values(values.get("priority", current.priority), now))
            else:
                values.update(sla.status_values(current, status, now))
            Ticket.objects.filter(Q(automated=True) | Q(status=Status.SPAM), pk=current.pk).update(
                **values, updated_at=now
            )
            moved = {"from": current.classification, "to": "human"}
            if relayed:
                alias = _alias(_opening(current), relayed["requester_name"])
                moved.update(requester=relayed["requester_email"], **({"alias": True} if alias else {}))
            events.record(current, Kind.RECLASSIFIED, actor=actor, **moved)
        count += 1
    return count
