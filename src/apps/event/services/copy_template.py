"""Build safe, detached snapshots for the Event admin copy flow."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apps.event.models import Event


@dataclass(frozen=True, slots=True)
class TicketCopySnapshot:
    name: str
    order: int

    def as_initial(self) -> dict[str, Any]:
        return {"name": self.name, "order": self.order}


@dataclass(frozen=True, slots=True)
class QuestionCopySnapshot:
    text: str
    is_required: bool
    order: int

    def as_initial(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "is_required": self.is_required,
            "order": self.order,
        }


@dataclass(frozen=True, slots=True)
class EventCopyTemplate:
    """A safe allow-listed snapshot that no longer depends on the source row."""

    source_id: UUID
    source_name: str
    event_initial: dict[str, Any]
    tickets: tuple[TicketCopySnapshot, ...]
    questions: tuple[QuestionCopySnapshot, ...]

    @property
    def ticket_count(self) -> int:
        return len(self.tickets)

    @property
    def question_count(self) -> int:
        return len(self.questions)

    def ticket_initial(self) -> list[dict[str, Any]]:
        return [ticket.as_initial() for ticket in self.tickets]

    def question_initial(self) -> list[dict[str, Any]]:
        return [question.as_initial() for question in self.questions]


def build_event_copy_template(source: Event) -> EventCopyTemplate:
    """Snapshot only fields that are safe to prefill into a new Event.

    Identity, registration state, Google Sheet state, and related operational
    data are deliberately reset or omitted. Related form rows are materialized
    in deterministic order and contain no source primary keys or barcodes.
    """

    source_tickets = sorted(
        source.tickets.all(),
        key=lambda ticket: (ticket.order, ticket.name, str(ticket.pk)),
    )
    source_questions = sorted(
        source.questions.all(),
        key=lambda question: (question.order, str(question.pk)),
    )
    tickets = tuple(TicketCopySnapshot(name=ticket.name, order=ticket.order) for ticket in source_tickets)
    questions = tuple(
        QuestionCopySnapshot(
            text=question.text,
            is_required=question.is_required,
            order=question.order,
        )
        for question in source_questions
    )

    return EventCopyTemplate(
        source_id=source.pk,
        source_name=source.name,
        event_initial={
            "name": "",
            "slug": "",
            "date": source.date,
            "end_date": source.effective_end_date,
            "location": source.location,
            "description": source.description,
            "registration_open": False,
            "allow_secondary_email": source.allow_secondary_email,
            "collect_phone": source.collect_phone,
            "verify_phone": source.verify_phone,
            "ticket_login_validity_days": source.ticket_login_validity_days,
            "ticket_login_reusable": source.ticket_login_reusable,
            "registration_sheet_id": "",
            "registration_sheet_gid": None,
        },
        tickets=tickets,
        questions=questions,
    )
