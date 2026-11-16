from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import Ticket
from apps.event.tests.helpers import make_event, make_member


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
