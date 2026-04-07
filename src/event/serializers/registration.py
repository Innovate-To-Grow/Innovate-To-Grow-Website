from rest_framework import serializers

from authn.models.contact.phone_regions import PHONE_REGION_CHOICES
from event.services import generate_ticket_barcode_data_url


class RegistrationAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    answer = serializers.CharField(allow_blank=True, max_length=2000)


class EventRegistrationCreateSerializer(serializers.Serializer):
    event_slug = serializers.SlugField()
    ticket_id = serializers.UUIDField()
    answers = RegistrationAnswerInputSerializer(many=True, required=False, default=list)
    attendee_first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    attendee_last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    attendee_organization = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    attendee_secondary_email = serializers.EmailField(required=False, allow_blank=True, default="")
    attendee_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    attendee_phone_region = serializers.CharField(max_length=10, required=False, default="1-US")
    phone_verified = serializers.BooleanField(required=False, default=False)


def _serialize_ticket_option(ticket) -> dict:
    return {
        "id": str(ticket.pk),
        "name": ticket.name,
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
        "attendee_first_name": registration.attendee_first_name,
        "attendee_last_name": registration.attendee_last_name,
        "attendee_name": registration.attendee_name,
        "attendee_email": registration.attendee_email,
        "attendee_secondary_email": registration.attendee_secondary_email,
        "attendee_phone": registration.attendee_phone,
        "phone_verified": registration.phone_verified,
        "phone_verification_required": (
            registration.event.verify_phone and registration.attendee_phone and not registration.phone_verified
        ),
        "attendee_organization": registration.attendee_organization,
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
        },
        "answers": registration.question_answers,
    }


def _get_member_emails(user) -> list[str]:
    contacts = user.contact_emails.filter(email_type__in=["primary", "secondary"]).order_by("email_type", "created_at")
    return [c.email_address for c in contacts]


def _get_member_profile(user) -> dict:
    return {
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "organization": getattr(user, "organization", "") or "",
    }


def _get_member_phone(user) -> dict | None:
    phone = user.contact_phones.order_by("-verified", "created_at").first()
    if phone is None:
        return None
    return {
        "phone_number": phone.phone_number,
        "region": phone.region,
        "verified": phone.verified,
    }


def build_event_registration_option_payload(event, registration=None, request=None) -> dict:
    member_emails = []
    member_profile = None
    member_phone = None
    if request and getattr(request, "user", None) and request.user.is_authenticated:
        member_emails = _get_member_emails(request.user)
        member_profile = _get_member_profile(request.user)
        member_phone = _get_member_phone(request.user)
    return {
        "id": str(event.pk),
        "name": event.name,
        "slug": event.slug,
        "date": event.date.isoformat(),
        "location": event.location,
        "description": event.description,
        "allow_secondary_email": event.allow_secondary_email,
        "collect_phone": event.collect_phone,
        "verify_phone": event.verify_phone,
        "tickets": [_serialize_ticket_option(ticket) for ticket in event.tickets.all()],
        "questions": [_serialize_question(question) for question in event.questions.all()],
        "registration": build_registration_payload(registration, request=request) if registration else None,
        "member_emails": member_emails,
        "member_profile": member_profile,
        "member_phone": member_phone,
        "phone_regions": [{"code": code, "label": label} for code, label in PHONE_REGION_CHOICES],
    }
