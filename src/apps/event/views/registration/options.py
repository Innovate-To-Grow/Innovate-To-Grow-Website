from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event.models import Event, EventRegistration
from apps.event.serializers import (
    build_event_registration_option_payload,
    build_event_registration_summary_payload,
)


def open_registration_events_queryset():
    return (
        Event.objects.filter(registration_open=True).order_by("date", "name").prefetch_related("questions", "tickets")
    )


def registration_for_events(user, events):
    if not user.is_authenticated:
        return {}
    registrations = (
        EventRegistration.objects.filter(member=user, event__in=events)
        .select_related("event", "ticket")
        .order_by("-created_at")
    )
    return {registration.event_id: registration for registration in registrations}


class EventRegistrationEventsView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        events = list(open_registration_events_queryset())
        registrations_by_event = registration_for_events(request.user, events)
        return Response(
            [
                build_event_registration_summary_payload(
                    event,
                    registration=registrations_by_event.get(event.pk),
                    request=request,
                )
                for event in events
            ]
        )


class EventRegistrationOptionsView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic,PyProtectedMember
    def get(self, request):
        event_slug = request.query_params.get("event_slug") or request.query_params.get("event")
        events_qs = open_registration_events_queryset()
        if event_slug:
            event = events_qs.filter(slug=event_slug).first()
            if event is None:
                return Response(
                    {"detail": "Event not found or not currently accepting registrations."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            events = list(events_qs)
            if len(events) > 1:
                registrations_by_event = registration_for_events(request.user, events)
                return Response(
                    {
                        "detail": "Please choose an event.",
                        "events": [
                            build_event_registration_summary_payload(
                                event,
                                registration=registrations_by_event.get(event.pk),
                                request=request,
                            )
                            for event in events
                        ],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            event = events[0] if events else None

        if event is None:
            return Response(
                {"detail": "No event is currently accepting registrations."},
                status=status.HTTP_404_NOT_FOUND,
            )

        registration = None
        if request.user.is_authenticated:
            registration = (
                EventRegistration.objects.filter(member=request.user, event=event)
                .select_related("event", "ticket")
                .first()
            )

        return Response(
            build_event_registration_option_payload(
                event,
                registration=registration,
                request=request,
            )
        )
