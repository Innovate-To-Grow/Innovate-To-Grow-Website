import uuid
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import ContactPhone

from event.models import EventRegistration, Question, Ticket
from event.tests.helpers import make_event, make_member


class EventRegistrationCreateViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member(first_name="Jane", last_name="Doe")
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")

    def _post(self, data=None, authenticate=True):
        if authenticate:
            self.client.force_authenticate(self.member)
        if data is None:
            data = {"event_slug": self.event.slug, "ticket_id": str(self.ticket.pk)}
        return self.client.post("/event/registrations/", data, format="json")

    def test_unauthenticated_returns_401(self):
        response = self._post(authenticate=False)
        self.assertEqual(response.status_code, 401)

    def test_event_not_found_returns_404(self):
        response = self._post({"event_slug": "nonexistent", "ticket_id": str(self.ticket.pk)})
        self.assertEqual(response.status_code, 404)

    def test_non_live_event_returns_404(self):
        self.event.is_live = False
        self.event.save()
        response = self._post()
        self.assertEqual(response.status_code, 404)

    def test_invalid_ticket_returns_400(self):
        response = self._post({"event_slug": self.event.slug, "ticket_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 400)

    def test_ticket_from_wrong_event_returns_400(self):
        other_event = make_event(name="Other", slug="other")
        other_ticket = Ticket.objects.create(event=other_event, name="VIP")
        response = self._post({"event_slug": self.event.slug, "ticket_id": str(other_ticket.pk)})
        self.assertEqual(response.status_code, 400)

    def test_successful_registration_returns_201(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)

    def test_response_contains_registration_payload(self):
        response = self._post()
        self.assertIn("id", response.data)
        self.assertIn("ticket_code", response.data)
        self.assertIn("barcode_image", response.data)

    def test_duplicate_registration_returns_409(self):
        self._post()
        response = self._post()
        self.assertEqual(response.status_code, 409)
        self.assertIn("already registered", response.data["detail"])

    def test_duplicate_registration_includes_existing_payload(self):
        self._post()
        response = self._post()
        self.assertIn("registration", response.data)
        self.assertIn("id", response.data["registration"])

    def test_required_question_missing_answer_returns_400(self):
        Question.objects.create(event=self.event, text="Required Q", is_required=True)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Answer required", response.data["detail"])

    def test_required_question_blank_answer_returns_400(self):
        q = Question.objects.create(event=self.event, text="Required Q", is_required=True)
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "answers": [{"question_id": str(q.pk), "answer": "   "}],
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 400)

    def test_optional_question_can_be_blank(self):
        q = Question.objects.create(event=self.event, text="Optional Q", is_required=False)
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "answers": [{"question_id": str(q.pk), "answer": ""}],
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 201)

    def test_invalid_question_id_returns_400(self):
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "answers": [{"question_id": str(uuid.uuid4()), "answer": "answer"}],
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid question", response.data["detail"])

    def test_answers_stored_in_question_answers_field(self):
        q = Question.objects.create(event=self.event, text="Your role?", is_required=False)
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "answers": [{"question_id": str(q.pk), "answer": "Student"}],
        }
        self._post(data)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(len(reg.question_answers), 1)
        self.assertEqual(reg.question_answers[0]["answer"], "Student")

    def test_attendee_fields_from_request_data(self):
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_first_name": "Custom",
            "attendee_last_name": "Name",
        }
        self._post(data)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_first_name, "Custom")
        self.assertEqual(reg.attendee_last_name, "Name")

    def test_attendee_fields_fallback_to_member(self):
        self._post()
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_first_name, "Jane")
        self.assertEqual(reg.attendee_last_name, "Doe")

    def test_required_question_with_valid_answer_succeeds(self):
        q = Question.objects.create(event=self.event, text="Required Q", is_required=True)
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "answers": [{"question_id": str(q.pk), "answer": "My answer"}],
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 201)

    # ---------- Feature-flag gating ----------

    def test_secondary_email_stored_when_flag_on(self):
        self.event.allow_secondary_email = True
        self.event.save()
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_secondary_email": "second@example.com",
        }
        self._post(data)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_secondary_email, "second@example.com")

    def test_secondary_email_ignored_when_flag_off(self):
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_secondary_email": "second@example.com",
        }
        self._post(data)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_secondary_email, "")

    def test_phone_stored_when_flag_on(self):
        self.event.collect_phone = True
        self.event.save()
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_phone": "+15551234567",
        }
        self._post(data)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_phone, "+15551234567")

    def test_phone_ignored_when_flag_off(self):
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_phone": "+15551234567",
        }
        self._post(data)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_phone, "")

    def test_verified_phone_required_when_event_requires_it(self):
        self.event.collect_phone = True
        self.event.verify_phone = True
        self.event.save(update_fields=["collect_phone", "verify_phone"])
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_phone": "+15551234567",
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Please verify your phone number before completing registration.")

    @patch("event.services.ticket_mail.send_ticket_email")
    def test_account_verified_phone_accepted_without_sms_session_cache(self, _mock_ticket_email):
        """Pre-filled verified phone from profile must work without re-running SMS for this session."""
        self.event.collect_phone = True
        self.event.verify_phone = True
        self.event.save(update_fields=["collect_phone", "verify_phone"])
        ContactPhone.objects.create(
            member=self.member,
            phone_number="+15551234567",
            region="1-US",
            verified=True,
        )
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_phone": "5551234567",
            "attendee_phone_region": "1-US",
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 201)
        reg = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(reg.attendee_phone, "+15551234567")
        self.assertTrue(reg.phone_verified)

    def test_phone_is_required_when_verification_is_enabled(self):
        self.event.collect_phone = True
        self.event.verify_phone = True
        self.event.save(update_fields=["collect_phone", "verify_phone"])
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "A verified phone number is required for this event.")
