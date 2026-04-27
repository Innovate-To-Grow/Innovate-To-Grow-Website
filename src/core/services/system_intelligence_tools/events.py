from typing import Any

from django.db.models import Count

from core.services.system_intelligence_actions.exceptions import ActionRequestError
from core.services.system_intelligence_actions.utils import json_safe

from .query_helpers import object_payload, queryset_payload, require_one
from .runtime import run_action_service_async

EVENT_FIELDS = [
    "id",
    "name",
    "slug",
    "date",
    "location",
    "description",
    "is_live",
    "allow_secondary_email",
    "collect_phone",
    "verify_phone",
    "created_at",
    "updated_at",
]


async def get_event_detail(
    event_id: str | None = None, slug: str | None = None, name: str | None = None
) -> dict[str, Any]:
    """Get event settings, ticket types, questions, registrations, and check-in counts."""
    return await run_action_service_async(_get_event_detail, event_id, slug, name)


async def search_event_registrations(
    event_id: str | None = None,
    event_name: str | None = None,
    email: str | None = None,
    ticket_id: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Search event registrations by event, attendee email, or ticket type."""
    return await run_action_service_async(_search_event_registrations, event_id, event_name, email, ticket_id, limit)


async def get_registration_detail(registration_id: str | None = None, ticket_code: str | None = None) -> dict[str, Any]:
    """Get one event registration including answers and check-in records."""
    return await run_action_service_async(_get_registration_detail, registration_id, ticket_code)


async def get_ticket_capacity_summary(event_id: str | None = None, event_name: str | None = None) -> dict[str, Any]:
    """Summarize ticket types and registration counts for an event."""
    return await run_action_service_async(_get_ticket_capacity_summary, event_id, event_name)


async def get_checkin_breakdown(event_id: str | None = None, event_name: str | None = None) -> dict[str, Any]:
    """Summarize check-ins by station for an event."""
    return await run_action_service_async(_get_checkin_breakdown, event_id, event_name)


async def get_event_question_summary(event_id: str | None = None, event_name: str | None = None) -> dict[str, Any]:
    """List registration questions and sample submitted answers for an event."""
    return await run_action_service_async(_get_event_question_summary, event_id, event_name)


def _find_event(event_id: str | None = None, slug: str | None = None, name: str | None = None):
    from event.models import Event

    qs = Event.objects.all()
    if event_id:
        return require_one(qs.filter(pk=event_id), "Event")
    if slug:
        return require_one(qs.filter(slug=slug), "Event")
    if name:
        return require_one(qs.filter(name__icontains=name).order_by("-date"), "Event")
    raise ActionRequestError("Provide event_id, slug, or name.")


def _get_event_detail(event_id: str | None = None, slug: str | None = None, name: str | None = None) -> dict[str, Any]:
    event = _find_event(event_id, slug, name)
    return {
        "event": object_payload(event, EVENT_FIELDS),
        "tickets": queryset_payload(event.tickets.all(), ["id", "name", "order", "created_at"], limit=50)["rows"],
        "questions": queryset_payload(event.questions.all(), ["id", "text", "is_required", "order"], limit=50)["rows"],
        "counts": {
            "registrations": event.registrations.count(),
            "tickets": event.tickets.count(),
            "questions": event.questions.count(),
            "check_in_stations": event.check_ins.count(),
            "check_in_records": event.check_ins.aggregate(total=Count("records"))["total"] or 0,
        },
    }


def _registration_queryset(event_id=None, event_name=None, email=None, ticket_id=None):
    from event.models import EventRegistration

    qs = EventRegistration.objects.select_related("event", "ticket", "member")
    if event_id:
        qs = qs.filter(event_id=event_id)
    if event_name:
        qs = qs.filter(event__name__icontains=event_name)
    if email:
        qs = qs.filter(attendee_email__icontains=email)
    if ticket_id:
        qs = qs.filter(ticket_id=ticket_id)
    return qs


def _search_event_registrations(
    event_id=None, event_name=None, email=None, ticket_id=None, limit=None
) -> dict[str, Any]:
    qs = _registration_queryset(event_id, event_name, email, ticket_id).annotate(
        check_in_count=Count("check_in_records")
    )
    return queryset_payload(
        qs.order_by("-created_at"),
        [
            "id",
            "event__name",
            "ticket__name",
            "attendee_first_name",
            "attendee_last_name",
            "attendee_email",
            "attendee_organization",
            "phone_verified",
            "check_in_count",
            "created_at",
        ],
        limit=limit,
    )


def _get_registration_detail(registration_id: str | None = None, ticket_code: str | None = None) -> dict[str, Any]:
    from event.models import EventRegistration

    qs = EventRegistration.objects.select_related("event", "ticket", "member").prefetch_related("check_in_records")
    if registration_id:
        registration = require_one(qs.filter(pk=registration_id), "Registration")
    elif ticket_code:
        registration = require_one(qs.filter(ticket_code=ticket_code), "Registration")
    else:
        raise ActionRequestError("Provide registration_id or ticket_code.")
    return {
        "registration": object_payload(
            registration,
            [
                "id",
                "event_id",
                "ticket_id",
                "ticket_code",
                "attendee_first_name",
                "attendee_last_name",
                "attendee_email",
                "attendee_secondary_email",
                "attendee_phone",
                "phone_verified",
                "attendee_organization",
                "question_answers",
                "created_at",
                "updated_at",
            ],
        ),
        "event": object_payload(registration.event, ["id", "name", "slug", "date", "location"]),
        "ticket": object_payload(registration.ticket, ["id", "name", "order"]),
        "check_ins": queryset_payload(
            registration.check_in_records.select_related("check_in"),
            ["id", "check_in__name", "created_at"],
            limit=50,
        )["rows"],
    }


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
