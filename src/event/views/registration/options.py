from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import Event, EventRegistration
from event.serializers import build_event_registration_option_payload


class EventRegistrationOptionsView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic,PyProtectedMember
    def get(self, request):
        event = Event.objects.filter(is_live=True).prefetch_related("questions").prefetch_related("tickets").first()
        if event is None:
            return Response(
                {"detail": "No live event available."},
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
