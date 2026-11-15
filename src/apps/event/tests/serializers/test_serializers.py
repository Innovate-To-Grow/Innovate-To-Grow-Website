import uuid

from django.test import SimpleTestCase, TestCase

from apps.event.models import Question, Ticket
from apps.event.serializers.registration import (
    EventRegistrationCreateSerializer,
    RegistrationAnswerInputSerializer,
    _serialize_question,
    _serialize_ticket_option,
)
from apps.event.tests.helpers import make_event

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
    def _minimal(self, **overrides):
        data = {
            "event_slug": "demo-day",
            "ticket_id": str(uuid.uuid4()),
            "attendee_first_name": "John",
            "attendee_last_name": "Doe",
        }
        data.update(overrides)
        return data

    def test_valid_minimal_data(self):
        s = EventRegistrationCreateSerializer(data=self._minimal())
        self.assertTrue(s.is_valid())

    def test_valid_full_data(self):
        data = self._minimal(
            attendee_organization="Acme",
            answers=[{"question_id": str(uuid.uuid4()), "answer": "Yes"}],
        )
        s = EventRegistrationCreateSerializer(data=data)
        self.assertTrue(s.is_valid())

    def test_missing_event_slug_invalid(self):
        data = self._minimal()
        del data["event_slug"]
        s = EventRegistrationCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("event_slug", s.errors)

    def test_missing_ticket_id_invalid(self):
        data = self._minimal()
        del data["ticket_id"]
        s = EventRegistrationCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("ticket_id", s.errors)

    def test_answers_default_to_empty_list(self):
        s = EventRegistrationCreateSerializer(data=self._minimal())
        s.is_valid()
        self.assertEqual(s.validated_data["answers"], [])

    def test_missing_attendee_first_name_invalid(self):
        data = self._minimal()
        del data["attendee_first_name"]
        s = EventRegistrationCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("attendee_first_name", s.errors)

    def test_missing_attendee_last_name_invalid(self):
        data = self._minimal()
        del data["attendee_last_name"]
        s = EventRegistrationCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("attendee_last_name", s.errors)

    def test_blank_attendee_last_name_invalid(self):
        s = EventRegistrationCreateSerializer(data=self._minimal(attendee_last_name=""))
        self.assertFalse(s.is_valid())
        self.assertIn("attendee_last_name", s.errors)


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


# ---------- build_event_registration_option_payload ----------
