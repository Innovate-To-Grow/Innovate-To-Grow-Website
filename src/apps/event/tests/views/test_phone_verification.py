from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import PhoneVerificationChallenge
from apps.event.models import EventRegistration, Ticket
from apps.event.tests.helpers import make_event, make_member
from apps.event.views.registration.phones import (
    LEGACY_EVENT_REGISTRATION_CONTEXT,
)


class PhoneVerificationViewsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)
        self.event = make_event(registration_open=True, collect_phone=True, verify_phone=True)

    @patch("apps.authn.services.sms.start_phone_verification", side_effect=RuntimeError("provider down"))
    def test_send_phone_code_returns_generic_service_error(self, _mock_start):
        with patch("apps.event.views.registration.logger.warning") as warning:
            response = self.client.post(
                "/event/send-phone-code/",
                {
                    "phone": "5551234567",
                    "region": "1-US",
                    "event_slug": self.event.slug,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Failed to send verification code. Please try again later.")
        warning.assert_called_once_with("Failed to send phone verification SMS", exc_info=True)

    @patch("apps.authn.services.sms.check_phone_verification", side_effect=RuntimeError("provider down"))
    def test_verify_phone_code_returns_generic_service_error(self, _mock_check):
        with patch("apps.event.views.registration.logger.warning") as warning:
            response = self.client.post(
                "/event/verify-phone-code/",
                {
                    "phone": "+15551234567",
                    "code": "123456",
                    "event_slug": self.event.slug,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Verification service is unavailable. Please try again later.")
        warning.assert_called_once_with("Phone verification failed", exc_info=True)

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_verified_phone_proof_is_consumed_by_registration(self, _mock_ticket_email):
        ticket = Ticket.objects.create(event=self.event, name="GA")
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number="+15551234567",
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=self.member,
            context_identifier=f"event-registration:{self.event.pk}",
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        verify_response = self.client.post(
            "/event/verify-phone-code/",
            {
                "phone": "+15551234567",
                "code": "123456",
                "challenge_id": str(challenge.pk),
                "event_slug": self.event.slug,
            },
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["phone"], "+15551234567")

        register_response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": self.event.slug,
                "ticket_id": str(ticket.pk),
                "attendee_first_name": "Jane",
                "attendee_last_name": "Doe",
                "attendee_phone": "5551234567",
                "attendee_phone_region": "1-US",
                "phone_verification_challenge_id": str(challenge.pk),
            },
            format="json",
        )
        self.assertEqual(register_response.status_code, 201)

        registration = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertEqual(registration.attendee_phone, "+15551234567")
        self.assertTrue(registration.phone_verified)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.CONSUMED)

        second_event = make_event(
            name="Second Demo Day",
            slug="second-demo-day",
            registration_open=True,
            collect_phone=True,
            verify_phone=True,
        )
        second_ticket = Ticket.objects.create(event=second_event, name="VIP")
        replay_response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": second_event.slug,
                "ticket_id": str(second_ticket.pk),
                "attendee_first_name": "Jane",
                "attendee_last_name": "Doe",
                "attendee_phone": "5551234567",
                "attendee_phone_region": "1-US",
            },
            format="json",
        )
        # SMS proof is one-use, but the first registration synced a verified ContactPhone for this member,
        # so a later event can reuse that account-verified number without a new SMS.
        self.assertEqual(replay_response.status_code, 201)

        second_member = make_member(email="other@example.com")
        self.client.force_authenticate(second_member)
        second_response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": second_event.slug,
                "ticket_id": str(second_ticket.pk),
                "attendee_first_name": "Other",
                "attendee_last_name": "Person",
                "attendee_phone": "5551234567",
                "attendee_phone_region": "1-US",
            },
            format="json",
        )
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(
            second_response.data["detail"], "Please verify your phone number before completing registration."
        )

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_legacy_phone_only_grant_is_bound_and_consumed_at_registration(
        self,
        _mock_ticket_email,
    ):
        make_event(
            name="Another Eligible Event",
            slug="another-eligible-event",
            registration_open=True,
            collect_phone=True,
            verify_phone=True,
        )
        ticket = Ticket.objects.create(event=self.event, name="GA")
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number="+15551234567",
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=self.member,
            context_identifier=LEGACY_EVENT_REGISTRATION_CONTEXT,
            code_hash=make_password("123456"),
            status=PhoneVerificationChallenge.Status.VERIFIED,
            verified_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": self.event.slug,
                "ticket_id": str(ticket.pk),
                "attendee_first_name": "Legacy",
                "attendee_last_name": "Client",
                "attendee_phone": "5551234567",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        challenge.refresh_from_db()
        self.assertEqual(
            challenge.status,
            PhoneVerificationChallenge.Status.CONSUMED,
        )


class PhoneValidationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)
        self.event = make_event(registration_open=True, collect_phone=True, verify_phone=True)

    def test_send_code_rejects_short_us_number(self):
        response = self.client.post(
            "/event/send-phone-code/",
            {
                "phone": "12345",
                "region": "1-US",
                "event_slug": self.event.slug,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("10 digits", response.data["detail"])

    @patch(
        "apps.authn.services.sms.start_phone_verification",
        return_value={"status": "pending", "challenge_id": "challenge-1"},
    )
    def test_send_code_ignores_client_region_and_pins_us(self, mock_start):
        # US-only: a client-supplied non-US region must be ignored, not used to build the E.164.
        response = self.client.post(
            "/event/send-phone-code/",
            {
                "phone": "5551234567",
                "region": "52",
                "event_slug": self.event.slug,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["phone"], "+15551234567")
        mock_start.assert_called_once_with(
            "+15551234567",
            purpose="event_registration",
            member=self.member,
            context_identifier=f"event-registration:{self.event.pk}",
        )

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_registration_rejects_invalid_phone(self, _mock_email):
        self.event.verify_phone = False
        self.event.save(update_fields=["verify_phone", "updated_at"])
        ticket = Ticket.objects.create(event=self.event, name="GA")
        response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": self.event.slug,
                "ticket_id": str(ticket.pk),
                "attendee_first_name": "Jane",
                "attendee_last_name": "Doe",
                "attendee_phone": "123",
                "attendee_phone_region": "1-US",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("10 digits", response.data["detail"])
