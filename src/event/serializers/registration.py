from rest_framework import serializers

from event.services import generate_ticket_barcode_data_url


class RegistrationAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    answer = serializers.CharField(allow_blank=True, max_length=2000)


class EventRegistrationCreateSerializer(serializers.Serializer):
    event_slug = serializers.SlugField()
    ticket_id = serializers.UUIDField()
    answers = RegistrationAnswerInputSerializer(many=True, required=False, default=list)


def _serialize_ticket_option(ticket) -> dict:
    registration_count = getattr(ticket, "registration_count", None)
    if registration_count is None:
        registration_count = ticket.registrations.count()
    remaining_quantity = None if ticket.quantity == 0 else max(ticket.quantity - registration_count, 0)
    return {
        "id": str(ticket.pk),
        "name": ticket.name,
        "price": f"{ticket.price:.2f}",
        "quantity": ticket.quantity,
        "remaining_quantity": remaining_quantity,
        "is_sold_out": remaining_quantity == 0 if remaining_quantity is not None else False,
    }


def _serialize_question(question) -> dict:
    return {
        "id": str(question.pk),
        "text": question.text,
        "is_required": question.is_required,
        "order": question.order,
    }


# noinspection PyUnusedLocal
def build_registration_payload(registration, request=None) -> dict:
    return {
        "id": str(registration.pk),
        "ticket_code": registration.ticket_code,
        "attendee_name": registration.attendee_name,
        "attendee_email": registration.attendee_email,
        "registered_at": registration.created_at.isoformat(),
        "ticket_email_sent_at": registration.ticket_email_sent_at.isoformat()
        if registration.ticket_email_sent_at
        else None,
        "ticket_email_error": registration.ticket_email_error,
        "barcode_format": "PDF417",
        "barcode_image": generate_ticket_barcode_data_url(registration),
        "event": {
            "id": str(registration.event.pk),
            "name": registration.event.name,
            "slug": registration.event.slug,
            "date": registration.event.date.isoformat(),
            "location": registration.event.location,
            "description": registration.event.description,
        },
        "ticket": {
            "id": str(registration.ticket.pk),
            "name": registration.ticket.name,
            "price": f"{registration.ticket.price:.2f}",
        },
        "answers": registration.question_answers,
    }


def build_event_registration_option_payload(event, registration=None, request=None) -> dict:
    return {
        "id": str(event.pk),
        "name": event.name,
        "slug": event.slug,
        "date": event.date.isoformat(),
        "location": event.location,
        "description": event.description,
        "tickets": [_serialize_ticket_option(ticket) for ticket in event.tickets.all()],
        "questions": [_serialize_question(question) for question in event.questions.all()],
        "registration": build_registration_payload(registration, request=request) if registration else None,
    }
