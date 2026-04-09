from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from event.models import EventRegistration, Ticket
from event.tests.helpers import make_event, make_member


class PhoneVerificationViewsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)

    @patch("authn.services.sms.start_phone_verification", side_effect=RuntimeError("provider down"))
    def test_send_phone_code_returns_generic_service_error(self, _mock_start):
        response = self.client.post(
            "/event/send-phone-code/",
            {"phone": "5551234567", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Failed to send verification code. Please try again later.")

    @patch("authn.services.sms.check_phone_verification", side_effect=RuntimeError("provider down"))
    def test_verify_phone_code_returns_generic_service_error(self, _mock_check):
        response = self.client.post(
            "/event/verify-phone-code/",
            {"phone": "+15551234567", "code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Verification service is unavailable. Please try again later.")

    @patch("event.services.ticket_mail.send_ticket_email")
    @patch("authn.services.sms.check_phone_verification", return_value="approved")
    def test_verified_phone_proof_is_consumed_by_registration(self, _mock_check, _mock_ticket_email):
        event = make_event(is_live=True, collect_phone=True, verify_phone=True)
        ticket = Ticket.objects.create(event=event, name="GA")

        verify_response = self.client.post(
            "/event/verify-phone-code/",
            {"phone": "+15551234567", "code": "123456"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["phone"], "+15551234567")

        register_response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": event.slug,
                "ticket_id": str(ticket.pk),
                "attendee_phone": "5551234567",
                "attendee_phone_region": "1-US",
            },
            format="json",
        )
        self.assertEqual(register_response.status_code, 201)

        registration = EventRegistration.objects.get(member=self.member, event=event)
        self.assertEqual(registration.attendee_phone, "+15551234567")
        self.assertTrue(registration.phone_verified)

        second_event = make_event(
            name="Second Demo Day", slug="second-demo-day", is_live=True, collect_phone=True, verify_phone=True
        )
        second_ticket = Ticket.objects.create(event=second_event, name="VIP")
        replay_response = self.client.post(
            "/event/registrations/",
            {
                "event_slug": second_event.slug,
                "ticket_id": str(second_ticket.pk),
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
                "attendee_phone": "5551234567",
                "attendee_phone_region": "1-US",
            },
            format="json",
        )
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(
            second_response.data["detail"], "Please verify your phone number before completing registration."
        )
