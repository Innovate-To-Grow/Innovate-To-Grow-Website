from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import ContactPhone
from apps.event.models import EventRegistration
from apps.event.tests.views.registration.create.test_registration_create import _EventRegistrationCreateViewCase


@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
class EventRegistrationCreateViewTest(_EventRegistrationCreateViewCase):
    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_account_verified_phone_accepted_without_sms_session_cache(self, _mock_ticket_email):
        """Pre-filled verified phone from profile must work without re-running SMS for this session."""
        self.event.collect_phone = True
        self.event.verify_phone = True
        self.event.save(update_fields=["collect_phone", "verify_phone"])
        ContactPhone.objects.create(
            member=self.member,
            phone_number="5551234567",
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

    def test_phone_is_required_only_when_required_is_enabled(self):
        self.event.collect_phone = True
        self.event.verify_phone = True
        self.event.require_phone = True
        self.event.save(update_fields=["collect_phone", "verify_phone", "require_phone"])
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "A phone number is required for this event.")
