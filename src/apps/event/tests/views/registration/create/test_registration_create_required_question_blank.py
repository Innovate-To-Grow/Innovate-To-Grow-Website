import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import override_settings
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.event.models import EventRegistration, Question
from apps.event.tests.views.registration.create.test_registration_create import _EventRegistrationCreateViewCase


@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
class EventRegistrationCreateViewTest(_EventRegistrationCreateViewCase):
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

    def test_missing_attendee_last_name_returns_400(self):
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "attendee_first_name": "Jane",
            "attendee_last_name": "",
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("attendee_last_name", response.data)

    def test_registration_failure_rolls_back_phone_proof_consumption(self):
        self.event.collect_phone = True
        self.event.verify_phone = True
        self.event.save(update_fields=["collect_phone", "verify_phone", "updated_at"])
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number="+15551234567",
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=self.member,
            context_identifier=f"event-registration:{self.event.pk}",
            code_hash=make_password("123456"),
            status=PhoneVerificationChallenge.Status.VERIFIED,
            verified_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.client.raise_request_exception = False

        with patch(
            "apps.event.views.registration.create.view.sync_registration_to_account",
            side_effect=RuntimeError("database follow-up failed"),
        ):
            response = self._post(
                {
                    "event_slug": self.event.slug,
                    "ticket_id": str(self.ticket.pk),
                    "attendee_first_name": "Jane",
                    "attendee_last_name": "Doe",
                    "attendee_phone": "5551234567",
                    "phone_verification_challenge_id": str(challenge.pk),
                }
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(EventRegistration.objects.filter(member=self.member, event=self.event).exists())
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.VERIFIED)

    def test_required_question_with_valid_answer_succeeds(self):
        q = Question.objects.create(event=self.event, text="Required Q", is_required=True)
        data = {
            "event_slug": self.event.slug,
            "ticket_id": str(self.ticket.pk),
            "answers": [{"question_id": str(q.pk), "answer": "My answer"}],
        }
        response = self._post(data)
        self.assertEqual(response.status_code, 201)

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
