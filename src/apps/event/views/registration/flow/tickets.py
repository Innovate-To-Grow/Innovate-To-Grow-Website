from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event.models import EventRegistration
from apps.event.serializers import build_registration_payload
from apps.event.throttles import TicketEmailResendThrottle


class MyTicketsView(APIView):
    rate_limit_scope = "member-read"
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        registrations = EventRegistration.objects.filter(member=request.user).select_related("event", "ticket")
        return Response([build_registration_payload(registration, request=request) for registration in registrations])


class ResendTicketEmailView(APIView):
    rate_limit_scope = "member-send"
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketEmailResendThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        import apps.event.views.registration as registration_api

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
            from apps.event.services.ticket.mail import send_ticket_email

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
