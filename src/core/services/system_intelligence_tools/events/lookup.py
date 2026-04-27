from typing import Any

from django.db.models import Count

from core.services.system_intelligence_actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async

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
