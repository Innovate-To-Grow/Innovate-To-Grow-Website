from django.db.models import Prefetch
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import Event, EventScheduleSection, EventScheduleTrack
from event.serializers import build_schedule_payload


class CurrentEventScheduleView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        event = (
            Event.objects.filter(is_live=True)
            .prefetch_related(
                "agenda_items",
                Prefetch(
                    "schedule_sections",
                    queryset=EventScheduleSection.objects.prefetch_related(
                        Prefetch("tracks", queryset=EventScheduleTrack.objects.prefetch_related("slots"))
                    ),
                ),
            )
            .first()
        )
        if event is None:
            return Response({"detail": "No live event available."}, status=status.HTTP_404_NOT_FOUND)

        if not event.schedule_sections.exists():
            return Response({"detail": "No live event schedule available."}, status=status.HTTP_404_NOT_FOUND)

        return Response(build_schedule_payload(event))
