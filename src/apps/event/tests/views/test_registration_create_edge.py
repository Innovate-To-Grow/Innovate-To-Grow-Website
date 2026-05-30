from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import EventRegistration, Ticket
from apps.event.tests.helpers import make_event, make_member, make_registration


class RegistrationCreateIntegrityErrorTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member(first_name="Jane", last_name="Doe")
        self.client.force_authenticate(self.member)
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")

    def _post(self):
        return self.client.post(
            "/event/registrations/",
            {
                "event_slug": self.event.slug,
                "ticket_id": str(self.ticket.pk),
                "attendee_first_name": "Jane",
                "attendee_last_name": "Doe",
            },
            format="json",
        )

    @patch("apps.event.views.registration.create.create_registration", side_effect=IntegrityError("dup"))
    @patch("apps.event.views.registration.create.existing_registration_response", return_value=None)
    def test_integrity_error_with_existing_row_returns_409_with_payload(self, _mock_existing, _mock_create):
        # A registration already exists (the racing winner), so duplicate_registration_response
        # finds it and includes its payload.
        existing = make_registration(self.member, self.event, self.ticket)

        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "You are already registered for this event.")
        self.assertIsNotNone(response.data["registration"])
        self.assertEqual(response.data["registration"]["id"], str(existing.pk))

    @patch("apps.event.views.registration.create.create_registration", side_effect=IntegrityError("dup"))
    @patch("apps.event.views.registration.create.existing_registration_response", return_value=None)
    def test_integrity_error_without_existing_row_returns_409_null_payload(self, _mock_existing, _mock_create):
        # No persisted registration -> duplicate_registration_response returns null registration.
        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "You are already registered for this event.")
        self.assertIsNone(response.data["registration"])
        self.assertFalse(EventRegistration.objects.filter(member=self.member, event=self.event).exists())
