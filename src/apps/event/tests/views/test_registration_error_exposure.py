"""Registration failures never echo exception text or tracebacks to the client (CWE-209)."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.services.email.challenges import AuthChallengeInvalid
from apps.authn.services.sms import PhoneVerificationInvalid
from apps.event.models import EventRegistration
from apps.event.services.registration.contacts import RegistrationContactError
from apps.event.tests.helpers import make_event, make_member, make_ticket
from apps.event.views.registration.create_support import RegistrationRequestError, create_registration

SENTINEL = "SENTINEL-7f3c-internal"
PHONE_DETAIL = "Please verify your phone number before completing registration."
EMAIL_DETAIL = "Please verify your secondary email before completing registration."


def _internal_failure(exc_type):
    """A lower-layer error whose message and cause both carry server-only details."""
    error = exc_type(f"{SENTINEL} arn:aws:sns:us-west-2:000000000000:internal")
    error.__cause__ = RuntimeError(f"{SENTINEL} at /srv/app/apps/authn/services/sms/checks.py:205")
    return error


def _contact_error_with_internal_message():
    error = RegistrationContactError(PHONE_DETAIL, code="phone_verification_required")
    # The exception's own message is diagnostic text; only ``detail`` is client-safe.
    error.args = (f"{SENTINEL} challenge=1234 member=internal",)
    return error


class RegistrationErrorExposureTest(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="primary@example.com", first_name="Jane", last_name="Doe")
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def _post(self, event, **data):
        ticket = make_ticket(event)
        return self.client.post(
            "/event/registrations/",
            {
                "event_slug": event.slug,
                "ticket_id": str(ticket.pk),
                "attendee_first_name": "Jane",
                "attendee_last_name": "Doe",
                **data,
            },
            format="json",
        )

    def _event(self, **flags):
        return make_event(name=f"Exposure {uuid.uuid4()}", registration_open=True, **flags)

    def assertNoSentinel(self, response):
        self.assertNotIn(SENTINEL, response.content.decode())

    def test_contact_error_responds_with_declared_detail_not_exception_text(self):
        event = self._event(collect_phone=True)
        with patch(
            "apps.event.views.registration.create_support.registration_contact_fields",
            side_effect=_contact_error_with_internal_message(),
        ):
            response = self._post(event, attendee_phone="2095551234")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": PHONE_DETAIL, "code": "phone_verification_required"})
        self.assertNoSentinel(response)
        self.assertFalse(EventRegistration.objects.filter(event=event).exists())

    def test_conversion_keeps_cause_server_side_only(self):
        event = self._event(collect_phone=True)
        original = _contact_error_with_internal_message()
        request = SimpleNamespace(user=self.member)
        with patch(
            "apps.event.views.registration.create_support.registration_contact_fields",
            side_effect=original,
        ):
            with self.assertRaises(RegistrationRequestError) as ctx:
                create_registration(request, event, make_ticket(event), [], {})
        self.assertIs(ctx.exception.__cause__, original)
        self.assertEqual(ctx.exception.response.data, {"detail": PHONE_DETAIL, "code": "phone_verification_required"})

    def test_phone_proof_failure_hides_lower_layer_message_and_cause(self):
        event = self._event(collect_phone=True, verify_phone=True)
        with patch(
            "apps.authn.services.sms.consume_verified_phone_challenge",
            side_effect=_internal_failure(PhoneVerificationInvalid),
        ):
            response = self._post(event, attendee_phone="2095551234", phone_verification_challenge_id=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": PHONE_DETAIL, "code": "phone_verification_required"})
        self.assertNoSentinel(response)

    def test_email_proof_failure_hides_lower_layer_message_and_cause(self):
        event = self._event(allow_secondary_email=True, verify_secondary_email=True)
        with patch(
            "apps.event.services.registration.contacts.consume_verification_token",
            side_effect=_internal_failure(AuthChallengeInvalid),
        ):
            response = self._post(
                event,
                attendee_secondary_email="secondary@example.com",
                secondary_email_verification_challenge_id=str(uuid.uuid4()),
                secondary_email_verification_token="proof",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": EMAIL_DETAIL, "code": "secondary_email_verification_required"})
        self.assertNoSentinel(response)

    def test_unexpected_failure_returns_generic_500_and_logs_details_server_side(self):
        event = self._event()
        self.client.raise_request_exception = False
        with (
            patch(
                "apps.event.views.registration.create.send_initial_ticket_email",
                side_effect=RuntimeError(f"{SENTINEL} db=postgres://internal"),
            ),
            self.assertLogs("django.request", level="ERROR") as logs,
        ):
            response = self._post(event)
        self.assertEqual(response.status_code, 500)
        self.assertNoSentinel(response)
        self.assertIn(SENTINEL, str(logs.records[0].exc_info[1]))
        self.assertFalse(EventRegistration.objects.filter(event=event).exists())
