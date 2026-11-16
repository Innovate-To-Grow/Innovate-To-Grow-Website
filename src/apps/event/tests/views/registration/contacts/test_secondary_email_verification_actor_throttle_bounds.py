from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import SendVerificationRequest
from apps.authn.services.email.challenges import AuthChallengeDeliveryError
from apps.core.tests.request_limits.helpers import view_limit
from apps.event.tests.helpers import make_event, make_member
from apps.event.tests.views.registration.contacts.test_secondary_email_verification import (
    SEND_PATH,
    _SecondaryEmailVerificationCase,
)


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class SecondaryEmailVerificationTests(_SecondaryEmailVerificationCase):
    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_actor_throttle_bounds_rotating_destinations(self, send):
        with view_limit(**{"view-code-send-email": (2, 3600)}):
            for index in range(2):
                response = self.client.post(
                    SEND_PATH, self._send_payload(email=f"address{index}@example.com"), format="json"
                )
                self.assertEqual(response.status_code, 200, response.data)
            response = self.client.post(SEND_PATH, self._send_payload(email="address3@example.com"), format="json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(send.call_count, 2)

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_resend_cooldown_prevents_second_delivery(self, send):
        first = self.client.post(SEND_PATH, self._send_payload(), format="json")
        second = self.client.post(SEND_PATH, self._send_payload(), format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 429, second.data)
        send.assert_called_once()

    @override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0, SEND_VERIFICATION_DESTINATION_HOURLY_LIMIT=1)
    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_destination_limit_is_shared_across_members_and_events(self, send):
        first = self.client.post(SEND_PATH, self._send_payload(), format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.client.force_authenticate(make_member(email="another@example.com"))
        other_event = make_event(
            name="Other", slug="other", registration_open=True, allow_secondary_email=True, verify_secondary_email=True
        )
        second = self.client.post(SEND_PATH, self._send_payload(event_slug=other_event.slug), format="json")
        self.assertEqual(second.status_code, 429, second.data)
        self.assertEqual(second.data["code"], "send_throttled")
        send.assert_called_once()

    @patch(
        "apps.event.views.registration.contacts.secondary_email.issue_email_challenge",
        side_effect=AuthChallengeDeliveryError("provider details", outcome="permanent"),
    )
    def test_delivery_failure_is_generic_and_recorded(self, issue):
        response = self.client.post(SEND_PATH, self._send_payload(), format="json")
        self.assertEqual(response.status_code, 503, response.data)
        self.assertNotIn("provider details", str(response.data))
        self.assertEqual(SendVerificationRequest.objects.get().status, "definitely_failed")
        issue.assert_called_once()
