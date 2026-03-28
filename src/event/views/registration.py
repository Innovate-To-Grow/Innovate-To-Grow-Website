import logging

from django.db import IntegrityError
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import Event, EventRegistration, Question, Ticket
from event.serializers import (
    EventRegistrationCreateSerializer,
    build_event_registration_option_payload,
    build_registration_payload,
)

logger = logging.getLogger(__name__)


class EventRegistrationOptionsView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic,PyProtectedMember
    def get(self, request):
        event = (
            Event.objects.filter(is_live=True)
            .prefetch_related("questions")
            .prefetch_related(
                "tickets",
            )
            .first()
        )
        if event is None:
            return Response({"detail": "No live event available."}, status=status.HTTP_404_NOT_FOUND)

        tickets = event.tickets.annotate(
            registration_count=Count("registrations", filter=Q(registrations__is_deleted=False))
        )
        event._prefetched_objects_cache["tickets"] = list(tickets)

        registration = None
        if request.user.is_authenticated:
            registration = (
                EventRegistration.objects.filter(member=request.user, event=event)
                .select_related("event", "ticket")
                .first()
            )

        return Response(build_event_registration_option_payload(event, registration=registration, request=request))


class EventRegistrationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = EventRegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            event = Event.objects.get(slug=data["event_slug"], is_live=True)
        except Event.DoesNotExist:
            return Response(
                {"detail": "Event not found or not currently accepting registrations."},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = (
            EventRegistration.objects.filter(member=request.user, event=event).select_related("event", "ticket").first()
        )
        if existing:
            return Response(
                {
                    "detail": "You are already registered for this event.",
                    "registration": build_registration_payload(existing, request=request),
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            ticket = Ticket.objects.get(pk=data["ticket_id"], event=event)
        except Ticket.DoesNotExist:
            return Response({"detail": "Invalid ticket for this event."}, status=status.HTTP_400_BAD_REQUEST)

        if ticket.quantity > 0:
            current_count = EventRegistration.objects.filter(ticket=ticket).count()
            if current_count >= ticket.quantity:
                return Response({"detail": "This ticket is sold out."}, status=status.HTTP_400_BAD_REQUEST)

        questions = {str(q.pk): q for q in Question.objects.filter(event=event)}
        required_ids = {qid for qid, q in questions.items() if q.is_required}
        answers = data.get("answers", [])
        answered_map = {str(a["question_id"]): a["answer"] for a in answers}

        for req_id in required_ids:
            if not answered_map.get(req_id, "").strip():
                q_text = questions[req_id].text
                return Response({"detail": f'Answer required for: "{q_text}"'}, status=status.HTTP_400_BAD_REQUEST)

        question_answers = []
        for a in answers:
            qid = str(a["question_id"])
            if qid not in questions:
                return Response(
                    {"detail": "One of your answers references an invalid question. Please reload and try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            question_answers.append(
                {
                    "question_id": qid,
                    "question_text": questions[qid].text,
                    "answer": a["answer"],
                }
            )

        try:
            create_kwargs = {
                "member": request.user,
                "event": event,
                "ticket": ticket,
                "question_answers": question_answers,
            }
            if data.get("attendee_first_name"):
                create_kwargs["attendee_first_name"] = data["attendee_first_name"]
            if data.get("attendee_last_name"):
                create_kwargs["attendee_last_name"] = data["attendee_last_name"]
            if data.get("attendee_organization"):
                create_kwargs["attendee_organization"] = data["attendee_organization"]
            registration = EventRegistration.objects.create(**create_kwargs)
        except IntegrityError:
            existing = (
                EventRegistration.objects.filter(member=request.user, event=event)
                .select_related("event", "ticket")
                .first()
            )
            return Response(
                {
                    "detail": "You are already registered for this event.",
                    "registration": build_registration_payload(existing, request=request) if existing else None,
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(build_registration_payload(registration, request=request), status=status.HTTP_201_CREATED)


class MyTicketsView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        registrations = EventRegistration.objects.filter(member=request.user).select_related("event", "ticket")
        return Response([build_registration_payload(r, request=request) for r in registrations])


class ResendTicketEmailView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        return Response({"detail": "Email sending is not configured."}, status=status.HTTP_501_NOT_IMPLEMENTED)
