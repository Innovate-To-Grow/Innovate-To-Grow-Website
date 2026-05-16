from typing import Any

from django.db.models import Count

from system_intelligence.services.actions.utils import json_safe

from ..query_helpers import object_payload, queryset_payload
from ..runtime import run_action_service_async
from .lookup import _find_event


async def get_ticket_capacity_summary(event_id: str | None = None, event_name: str | None = None) -> dict[str, Any]:
    """Summarize ticket types and registration counts for an event."""
    return await run_action_service_async(_get_ticket_capacity_summary, event_id, event_name)


async def get_checkin_breakdown(event_id: str | None = None, event_name: str | None = None) -> dict[str, Any]:
    """Summarize check-ins by station for an event."""
    return await run_action_service_async(_get_checkin_breakdown, event_id, event_name)


async def get_event_question_summary(event_id: str | None = None, event_name: str | None = None) -> dict[str, Any]:
    """List registration questions and sample submitted answers for an event."""
    return await run_action_service_async(_get_event_question_summary, event_id, event_name)


def _get_ticket_capacity_summary(event_id=None, event_name=None) -> dict[str, Any]:
    event = _find_event(event_id=event_id, name=event_name)
    tickets = event.tickets.annotate(registration_count=Count("registrations")).order_by("order", "name")
    return {
        "event": object_payload(event, ["id", "name", "slug", "date"]),
        "registration_count": event.registrations.count(),
        "tickets": queryset_payload(tickets, ["id", "name", "order", "registration_count"], limit=50)["rows"],
    }


def _get_checkin_breakdown(event_id=None, event_name=None) -> dict[str, Any]:
    from event.models import CheckInRecord

    event = _find_event(event_id=event_id, name=event_name)
    stations = event.check_ins.annotate(scan_count=Count("records")).order_by("name")
    unique_checked_in = CheckInRecord.objects.filter(check_in__event=event).values("registration_id").distinct().count()
    total_registrations = event.registrations.count()
    return {
        "event": object_payload(event, ["id", "name", "slug", "date"]),
        "total_registrations": total_registrations,
        "unique_checked_in": unique_checked_in,
        "not_checked_in": max(total_registrations - unique_checked_in, 0),
        "stations": queryset_payload(stations, ["id", "name", "is_active", "scan_count"], limit=50)["rows"],
    }


def _get_event_question_summary(event_id=None, event_name=None) -> dict[str, Any]:
    event = _find_event(event_id=event_id, name=event_name)
    questions = list(event.questions.values("id", "text", "is_required", "order"))
    samples = list(
        event.registrations.exclude(question_answers=[])
        .values("id", "attendee_email", "question_answers", "created_at")
        .order_by("-created_at")[:10]
    )
    return {
        "event": object_payload(event, ["id", "name", "slug", "date"]),
        "registration_count": event.registrations.count(),
        "questions": json_safe(questions),
        "sample_answers": json_safe(samples),
    }
