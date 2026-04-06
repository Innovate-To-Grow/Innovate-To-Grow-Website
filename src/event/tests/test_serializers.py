import datetime
import uuid

from django.test import SimpleTestCase, TestCase

from event.models import Event, EventRegistration, Question, Ticket
from event.serializers.registration import (
    EventRegistrationCreateSerializer,
    RegistrationAnswerInputSerializer,
    _serialize_question,
    _serialize_ticket_option,
    build_event_registration_option_payload,
    build_registration_payload,
)
from event.tests.helpers import make_event, make_member

# ---------- RegistrationAnswerInputSerializer ----------


class RegistrationAnswerInputSerializerTest(SimpleTestCase):
    def test_valid_data(self):
        data = {"question_id": str(uuid.uuid4()), "answer": "My answer"}
        s = RegistrationAnswerInputSerializer(data=data)
        self.assertTrue(s.is_valid())

    def test_blank_answer_allowed(self):
        data = {"question_id": str(uuid.uuid4()), "answer": ""}
        s = RegistrationAnswerInputSerializer(data=data)
        self.assertTrue(s.is_valid())

    def test_invalid_uuid_rejected(self):
        data = {"question_id": "not-a-uuid", "answer": "answer"}
        s = RegistrationAnswerInputSerializer(data=data)
        self.assertFalse(s.is_valid())

    def test_missing_question_id_invalid(self):
        data = {"answer": "answer"}
        s = RegistrationAnswerInputSerializer(data=data)
        self.assertFalse(s.is_valid())

    def test_missing_answer_invalid(self):
        data = {"question_id": str(uuid.uuid4())}
        s = RegistrationAnswerInputSerializer(data=data)
        self.assertFalse(s.is_valid())


# ---------- EventRegistrationCreateSerializer ----------


class EventRegistrationCreateSerializerTest(SimpleTestCase):
    def test_valid_minimal_data(self):
        data = {"event_slug": "demo-day", "ticket_id": str(uuid.uuid4())}
        s = EventRegistrationCreateSerializer(data=data)
        self.assertTrue(s.is_valid())

    def test_valid_full_data(self):
        data = {
            "event_slug": "demo-day",
            "ticket_id": str(uuid.uuid4()),
            "attendee_first_name": "John",
            "attendee_last_name": "Doe",
            "attendee_organization": "Acme",
            "answers": [{"question_id": str(uuid.uuid4()), "answer": "Yes"}],
        }
        s = EventRegistrationCreateSerializer(data=data)
        self.assertTrue(s.is_valid())

    def test_missing_event_slug_invalid(self):
        data = {"ticket_id": str(uuid.uuid4())}
        s = EventRegistrationCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("event_slug", s.errors)

    def test_missing_ticket_id_invalid(self):
        data = {"event_slug": "demo-day"}
        s = EventRegistrationCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("ticket_id", s.errors)

    def test_answers_default_to_empty_list(self):
        data = {"event_slug": "demo-day", "ticket_id": str(uuid.uuid4())}
        s = EventRegistrationCreateSerializer(data=data)
        s.is_valid()
        self.assertEqual(s.validated_data["answers"], [])

    def test_attendee_fields_optional(self):
        data = {"event_slug": "demo-day", "ticket_id": str(uuid.uuid4())}
        s = EventRegistrationCreateSerializer(data=data)
        self.assertTrue(s.is_valid())
        self.assertEqual(s.validated_data["attendee_first_name"], "")


# ---------- _serialize_ticket_option ----------


class SerializeTicketOptionTest(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_contains_id_and_name(self):
        ticket = Ticket.objects.create(event=self.event, name="GA")
        result = _serialize_ticket_option(ticket)
        self.assertEqual(result["id"], str(ticket.pk))
        self.assertEqual(result["name"], "GA")


# ---------- _serialize_question ----------


class SerializeQuestionTest(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_contains_expected_keys(self):
        q = Question.objects.create(event=self.event, text="Your role?", is_required=True, order=1)
        result = _serialize_question(q)
        self.assertEqual(result["id"], str(q.pk))
        self.assertEqual(result["text"], "Your role?")
        self.assertTrue(result["is_required"])
        self.assertEqual(result["order"], 1)


# ---------- build_registration_payload ----------


class BuildRegistrationPayloadTest(TestCase):
    def setUp(self):
        self.member = make_member(first_name="Jane", last_name="Doe")
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_contains_all_expected_keys(self):
        result = build_registration_payload(self.registration)
        expected_keys = {
            "id",
            "ticket_code",
            "attendee_first_name",
            "attendee_last_name",
            "attendee_name",
            "attendee_email",
            "attendee_secondary_email",
            "attendee_phone",
            "phone_verified",
            "phone_verification_required",
            "attendee_organization",
            "registered_at",
            "ticket_email_sent_at",
            "ticket_email_error",
            "barcode_format",
            "barcode_image",
            "event",
            "ticket",
            "answers",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_barcode_image_is_data_url(self):
        result = build_registration_payload(self.registration)
        self.assertTrue(result["barcode_image"].startswith("data:image/png;base64,"))

    def test_event_nested_dict_structure(self):
        result = build_registration_payload(self.registration)
        event_data = result["event"]
        self.assertEqual(event_data["name"], self.event.name)
        self.assertEqual(event_data["slug"], self.event.slug)

    def test_ticket_nested_dict_structure(self):
        result = build_registration_payload(self.registration)
        ticket_data = result["ticket"]
        self.assertEqual(ticket_data["name"], "GA")

    def test_ticket_email_sent_at_none_when_not_sent(self):
        result = build_registration_payload(self.registration)
        self.assertIsNone(result["ticket_email_sent_at"])

    def test_ticket_email_sent_at_formatted_when_set(self):
        from django.utils import timezone

        now = timezone.now()
        self.registration.ticket_email_sent_at = now
        self.registration.save()
        result = build_registration_payload(self.registration)
        self.assertEqual(result["ticket_email_sent_at"], now.isoformat())


# ---------- build_event_registration_option_payload ----------


class BuildEventRegistrationOptionPayloadTest(TestCase):
    def setUp(self):
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.question = Question.objects.create(event=self.event, text="Role?")

    def test_contains_event_fields(self):
        result = build_event_registration_option_payload(self.event)
        self.assertEqual(result["name"], self.event.name)
        self.assertEqual(result["slug"], self.event.slug)

    def test_tickets_list_serialized(self):
        result = build_event_registration_option_payload(self.event)
        self.assertEqual(len(result["tickets"]), 1)
        self.assertEqual(result["tickets"][0]["name"], "GA")

    def test_questions_list_serialized(self):
        result = build_event_registration_option_payload(self.event)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["text"], "Role?")

    def test_registration_none_when_not_provided(self):
        result = build_event_registration_option_payload(self.event)
        self.assertIsNone(result["registration"])

    def test_registration_included_when_provided(self):
        member = make_member()
        reg = EventRegistration.objects.create(member=member, event=self.event, ticket=self.ticket)
        result = build_event_registration_option_payload(self.event, registration=reg)
        self.assertIsNotNone(result["registration"])
        self.assertEqual(result["registration"]["id"], str(reg.pk))

    def test_empty_tickets_and_questions(self):
        event = Event.objects.create(name="Empty Event", date=datetime.date(2025, 7, 1), location="V", description="D")
        result = build_event_registration_option_payload(event)
        self.assertEqual(result["tickets"], [])
        self.assertEqual(result["questions"], [])
