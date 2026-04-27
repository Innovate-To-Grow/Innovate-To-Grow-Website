from typing import Any

from django.db.models import Count

from core.services.system_intelligence_actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async


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
