from django.db.models import Prefetch
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CurrentProjectSchedule, EventScheduleSection, EventScheduleTrack
from event.serializers import build_schedule_payload


class CurrentEventScheduleView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        config = CurrentProjectSchedule.load()
        if not config.pk:
            return Response({"detail": "No schedule configured."}, status=status.HTTP_404_NOT_FOUND)

        config = (
            CurrentProjectSchedule.objects.filter(pk=config.pk)
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
        if config is None:
            return Response({"detail": "No schedule configured."}, status=status.HTTP_404_NOT_FOUND)

        if not config.schedule_sections.exists():
            return Response({"detail": "No schedule available."}, status=status.HTTP_404_NOT_FOUND)

        return Response(build_schedule_payload(config))
