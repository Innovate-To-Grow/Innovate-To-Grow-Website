from rest_framework import status
from rest_framework.response import Response

from apps.event.models import Event, EventRegistration, Question, Ticket
from apps.event.serializers import build_registration_payload
from apps.event.services.registration.contacts import RegistrationContactError, registration_contact_fields
from apps.event.services.registration.sync_account import sync_name_to_account, sync_phone_to_account
from apps.event.services.registration.sync_email import sync_secondary_email_to_account

from .notifications import send_initial_ticket_email


class RegistrationRequestError(Exception):
    def __init__(self, detail: str, response_status=status.HTTP_400_BAD_REQUEST, *, code: str | None = None):
        self.response = Response({"detail": detail, **({"code": code} if code else {})}, status=response_status)
        super().__init__(detail)


def get_event(data):
    try:
        return Event.objects.get(slug=data["event_slug"], registration_open=True)
    except Event.DoesNotExist:
        return Response(
            {"detail": "Event not found or not currently accepting registrations."},
            status=status.HTTP_404_NOT_FOUND,
        )


def get_ticket(data, event):
    try:
        return Ticket.objects.get(pk=data["ticket_id"], event=event)
    except Ticket.DoesNotExist:
        return Response(
            {"detail": "Invalid ticket for this event."},
            status=status.HTTP_400_BAD_REQUEST,
        )


def existing_registration_response(request, event):
    existing = registration_for_user(request.user, event)
    if not existing:
        return None
    return Response(
        {
            "detail": "You are already registered for this event.",
            "registration": build_registration_payload(existing, request=request),
        },
        status=status.HTTP_409_CONFLICT,
    )


def duplicate_registration_response(request, event):
    existing = registration_for_user(request.user, event)
    return Response(
        {
            "detail": "You are already registered for this event.",
            "registration": (build_registration_payload(existing, request=request) if existing else None),
        },
        status=status.HTTP_409_CONFLICT,
    )


def registration_for_user(user, event):
    return EventRegistration.objects.filter(member=user, event=event).select_related("event", "ticket").first()


def question_answers_or_response(event, answers):
    questions = {str(question.pk): question for question in Question.objects.filter(event=event)}
    answered_map = {str(answer["question_id"]): answer["answer"] for answer in answers}
    for question_id, question in questions.items():
        if question.is_required and not answered_map.get(question_id, "").strip():
            return Response(
                {"detail": f'Answer required for: "{question.text}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    question_answers = []
    for answer in answers:
        question_id = str(answer["question_id"])
        if question_id not in questions:
            return Response(
                {"detail": ("One of your answers references an invalid question. Please reload and try again.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        question_answers.append(
            {
                "question_id": question_id,
                "question_text": questions[question_id].text,
                "answer": answer["answer"],
            }
        )
    return question_answers


def create_registration(request, event, ticket, question_answers, data):
    create_kwargs = registration_create_kwargs(
        request,
        event,
        ticket,
        question_answers,
        data,
    )
    try:
        create_kwargs.update(registration_contact_fields(request.user, event, data))
    except RegistrationContactError as exc:
        raise RegistrationRequestError(str(exc), code=exc.code) from exc
    return EventRegistration.objects.create(**create_kwargs)


def registration_create_kwargs(request, event, ticket, question_answers, data):
    create_kwargs = {
        "member": request.user,
        "event": event,
        "ticket": ticket,
        "question_answers": question_answers,
    }
    for field_name in (
        "attendee_first_name",
        "attendee_last_name",
        "attendee_organization",
    ):
        if data.get(field_name):
            create_kwargs[field_name] = data[field_name]
    return create_kwargs


def sync_registration_to_account(user, registration, event, data):
    sync_name_to_account(
        user,
        registration.attendee_first_name,
        registration.attendee_last_name,
    )
    if event.allow_secondary_email and registration.attendee_secondary_email:
        sync_secondary_email_to_account(
            user, registration.attendee_secondary_email, verified=registration.secondary_email_verified
        )
    if event.collect_phone and registration.attendee_phone:
        sync_phone_to_account(
            user,
            registration.attendee_phone,
            region="1-US",
            verified=registration.phone_verified,
        )
