"""Authenticated, event-scoped secondary email verification endpoints."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail, EmailAuthChallenge, SendVerificationRequest
from apps.authn.services.email.challenges import AuthChallengeDeliveryError
from apps.authn.services.send_verification.constants import OP_EVENT_SEND_SECONDARY_EMAIL_CODE
from apps.authn.tests.send_verification import mint_send_verification
from apps.event.tests.helpers import make_event, make_member

SEND_PATH = "/event/send-secondary-email-code/"
VERIFY_PATH = "/event/verify-secondary-email-code/"


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class SecondaryEmailVerificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="primary@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.member)
        self.event = make_event(registration_open=True, allow_secondary_email=True, verify_secondary_email=True)
        self.email = "secondary@example.com"
        self.context = f"event-registration:{self.event.pk}"

    def _send_payload(self, **overrides):
        data = {"event_slug": self.event.slug, "email": self.email, **overrides}
        return {**data, **mint_send_verification(self.client, OP_EVENT_SEND_SECONDARY_EMAIL_CODE, data)}

    def _challenge(self, **overrides):
        return EmailAuthChallenge.objects.create(
            **{
                "member": self.member,
                "purpose": EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
                "target_email": self.email,
                "context_identifier": self.context,
                "code_hash": make_password("123456"),
                "expires_at": timezone.now() + timedelta(minutes=10),
                **overrides,
            }
        )

    def _verify(self, challenge, **overrides):
        return self.client.post(
            VERIFY_PATH,
            {
                "event_slug": self.event.slug,
                "email": self.email,
                "challenge_id": str(challenge.pk),
                "code": "123456",
                **overrides,
            },
            format="json",
        )

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_send_returns_event_bound_challenge_without_creating_contact(self, send):
        contact_count = ContactEmail.objects.count()
        response = self.client.post(SEND_PATH, self._send_payload(email=self.email.upper()), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["email"], self.email)
        challenge = EmailAuthChallenge.objects.get(pk=response.data["challenge_id"])
        self.assertEqual(challenge.context_identifier, self.context)
        self.assertEqual(challenge.member, self.member)
        self.assertEqual(challenge.purpose, EmailAuthChallenge.Purpose.EVENT_REGISTRATION)
        self.assertEqual(ContactEmail.objects.count(), contact_count)
        self.assertEqual(send.call_args.kwargs["recipient"], self.email)

    def test_send_and_verify_require_authentication(self):
        challenge = self._challenge()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post(SEND_PATH, {}, format="json").status_code, 401)
        self.assertEqual(self._verify(challenge).status_code, 401)

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_send_requires_guard_before_email_side_effect(self, send):
        response = self.client.post(SEND_PATH, {"event_slug": self.event.slug, "email": self.email}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_required")
        self.assertFalse(EmailAuthChallenge.objects.exists())
        send.assert_not_called()

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_both_endpoints_reject_closed_or_disabled_event(self, send):
        challenge = self._challenge()
        for changes in (
            {"registration_open": False},
            {"verify_secondary_email": False},
            {"allow_secondary_email": False, "verify_secondary_email": False},
        ):
            with self.subTest(changes=changes):
                type(self.event).objects.filter(pk=self.event.pk).update(**changes)
                data = {"event_slug": self.event.slug, "email": self.email}
                self.assertEqual(self.client.post(SEND_PATH, data, format="json").status_code, 400)
                self.assertEqual(self._verify(challenge).status_code, 400)
                type(self.event).objects.filter(pk=self.event.pk).update(
                    registration_open=True, allow_secondary_email=True, verify_secondary_email=True
                )
        send.assert_not_called()

    def test_invalid_email_primary_email_and_missing_event_are_rejected(self):
        challenge = self._challenge()
        for email in ("not-an-email", "PRIMARY@example.com", ""):
            with self.subTest(email=email):
                response = self.client.post(SEND_PATH, {"event_slug": self.event.slug, "email": email}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self._verify(challenge, email=email).status_code, 400)
        self.assertEqual(self._verify(challenge, event_slug="unknown").status_code, 400)
        self.assertEqual(self.client.post(SEND_PATH, {"email": self.email}, format="json").status_code, 400)

    def test_verify_returns_token_without_upgrading_or_creating_contact(self):
        contact = ContactEmail.objects.create(member=self.member, email_address=self.email, email_type="secondary")
        challenge = self._challenge()
        response = self._verify(challenge)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["challenge_id"], str(challenge.pk))
        self.assertEqual(response.data["email"], self.email)
        self.assertTrue(response.data["verified"])
        self.assertTrue(response.data["verification_token"])
        contact.refresh_from_db()
        self.assertFalse(contact.verified)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.VERIFIED)
        self.assertEqual(self._verify(challenge).status_code, 400)

    def test_verify_rejects_wrong_member_event_email_purpose_and_challenge(self):
        challenge = self._challenge()
        other_event = make_event(
            name="Other", slug="other", registration_open=True, allow_secondary_email=True, verify_secondary_email=True
        )
        for changes in (
            {"event_slug": other_event.slug},
            {"email": "different@example.com"},
            {"challenge_id": str(uuid.uuid4())},
            {"challenge_id": "malformed"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self._verify(challenge, **changes).status_code, 400)
        self.client.force_authenticate(make_member(email="other@example.com"))
        self.assertEqual(self._verify(challenge).status_code, 400)
        self.client.force_authenticate(self.member)
        wrong_purpose = self._challenge(purpose=EmailAuthChallenge.Purpose.CONTACT_EMAIL_VERIFY)
        self.assertEqual(self._verify(wrong_purpose).status_code, 400)

    def test_verify_rejects_expiry_and_limits_wrong_attempts(self):
        expired = self._challenge(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._verify(expired).status_code, 400)
        challenge = self._challenge()
        for _ in range(challenge.max_attempts):
            self.assertEqual(self._verify(challenge, code="000000").status_code, 400)
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, challenge.max_attempts)
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.EXPIRED)
        self.assertEqual(self._verify(challenge).status_code, 400)

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_send_replay_does_not_resend_and_request_is_event_bound(self, send):
        payload = self._send_payload()
        first = self.client.post(SEND_PATH, payload, format="json")
        replay = self.client.post(SEND_PATH, payload, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(replay.data, first.data)
        other_event = make_event(
            name="Other", slug="other", registration_open=True, allow_secondary_email=True, verify_secondary_email=True
        )
        changed = self.client.post(SEND_PATH, {**payload, "event_slug": other_event.slug}, format="json")
        self.assertEqual(changed.status_code, 409, changed.data)
        self.assertEqual(changed.data["code"], "send_request_conflict")
        send.assert_called_once()

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_actor_throttle_bounds_rotating_destinations(self, send):
        from apps.event.throttles import EmailCodeUserRequestThrottle

        with patch.object(EmailCodeUserRequestThrottle, "THROTTLE_RATES", {"email_code_user_request": "2/hour"}):
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
        "apps.event.views.registration.secondary_email.issue_email_challenge",
        side_effect=AuthChallengeDeliveryError("provider details", outcome="permanent"),
    )
    def test_delivery_failure_is_generic_and_recorded(self, issue):
        response = self.client.post(SEND_PATH, self._send_payload(), format="json")
        self.assertEqual(response.status_code, 503, response.data)
        self.assertNotIn("provider details", str(response.data))
        self.assertEqual(SendVerificationRequest.objects.get().status, "definitely_failed")
        issue.assert_called_once()
