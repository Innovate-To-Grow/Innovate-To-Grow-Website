from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from event.serializers import EventRegistrationCreateSerializer, build_registration_payload

from .create_support import (
    RegistrationRequestError,
    create_registration,
    duplicate_registration_response,
    existing_registration_response,
    get_event,
    get_ticket,
    question_answers_or_response,
    send_initial_ticket_email,
    sync_registration_to_account,
)


class EventRegistrationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = EventRegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        event_response = get_event(data)
        if isinstance(event_response, Response):
            return event_response
        event = event_response

        existing_response = existing_registration_response(request, event)
        if existing_response:
            return existing_response

        ticket_response = get_ticket(data, event)
        if isinstance(ticket_response, Response):
            return ticket_response
        ticket = ticket_response

        answer_response = question_answers_or_response(event, data.get("answers", []))
        if isinstance(answer_response, Response):
            return answer_response

        try:
            registration = create_registration(
                request,
                event,
                ticket,
                answer_response,
                data,
            )
        except RegistrationRequestError as exc:
            return exc.response
        except IntegrityError:
            return duplicate_registration_response(request, event)

        sync_registration_to_account(request.user, registration, event, data)
        send_initial_ticket_email(registration)
        registration.refresh_from_db()
        return Response(
            build_registration_payload(registration, request=request),
            status=status.HTTP_201_CREATED,
        )
