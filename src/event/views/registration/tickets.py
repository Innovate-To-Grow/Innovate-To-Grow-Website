from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import EventRegistration
from event.serializers import build_registration_payload


class MyTicketsView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        registrations = EventRegistration.objects.filter(member=request.user).select_related("event", "ticket")
        return Response([build_registration_payload(registration, request=request) for registration in registrations])


class ResendTicketEmailView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        import event.views.registration as registration_api

        try:
            registration = EventRegistration.objects.select_related(
                "event",
                "ticket",
                "member",
            ).get(pk=pk, member=request.user)
        except EventRegistration.DoesNotExist:
            return Response(
                {"detail": "Registration not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            from event.services.ticket_mail import send_ticket_email

            send_ticket_email(registration)
        except Exception:
            registration_api.logger.warning(
                "Failed to send ticket email for registration",
                exc_info=True,
            )
            return Response(
                {"detail": "Failed to send email. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        registration.refresh_from_db()
        return Response(build_registration_payload(registration, request=request))
