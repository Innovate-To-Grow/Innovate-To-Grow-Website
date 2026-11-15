import uuid
from unittest.mock import patch

from django.test import Client, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.authn.tests.api.limits.degradation.test_no_ip_throttle import (
    BURST,
    CHALLENGE_URL,
    LONG_BURST,
    SEND_VIA_PROVIDER,
    STRONG_PASSWORD,
    Member,
    NoIpThrottleTestCase,
    make_member,
    rotating_forwarded_for,
)


class ChallengeIssuanceBurstTests(NoIpThrottleTestCase):
    """ALTCHA challenge issuance and status lookup: a challenge sends nothing, so it needs no per-IP cap."""

    def issue(self, index, **extra):
        return self.client.post(
            CHALLENGE_URL,
            {"operation": "login.request_code", "email": f"student{index}@example.com"},
            format="json",
            **extra,
        ).status_code

    def test_public_challenges_never_429(self):
        self.assertAll([self.issue(i) for i in range(BURST)], 200)

    def test_public_challenges_never_429_with_a_rotating_forwarded_for(self):
        self.assertAll([self.issue(i, **rotating_forwarded_for(i)) for i in range(BURST)], 200)

    def test_status_lookups_never_429(self):
        statuses = [
            self.client.get(f"/authn/send-verification/requests/{uuid.uuid4()}/").status_code for _ in range(LONG_BURST)
        ]

        self.assertNotIn(429, statuses)
        self.assertEqual(len(set(statuses)), 1, statuses)

    def test_admin_challenges_never_429(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("admin-login"))
        csrf = client.cookies["csrftoken"].value
        url = reverse("admin-send-verification-challenge")

        statuses = [
            client.post(
                url,
                {"operation": "admin.login.request_code", "email": f"staff{i}@example.com"},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
            ).status_code
            for i in range(BURST)
        ]

        self.assertAll(statuses, 200)


@patch(SEND_VIA_PROVIDER, return_value=True)
class EmailCodeRequestBurstTests(NoIpThrottleTestCase):
    """Real guard, test-mode proof handling: distinct destinations from one IP are never IP-throttled."""

    def test_login_code_requests_to_distinct_destinations_never_429(self, _ses):
        statuses = [
            self.client.post(
                "/authn/login/request-code/", {"email": f"login{i}@example.com"}, format="json"
            ).status_code
            for i in range(BURST)
        ]

        self.assertAll(statuses, 202)

    def test_unified_email_auth_requests_never_429(self, _ses):
        plain = [
            self.client.post(
                "/authn/email-auth/request-code/", {"email": f"unified{i}@example.com"}, format="json"
            ).status_code
            for i in range(BURST)
        ]
        # A rotating forged header would slip past a per-IP throttle keyed on it, so it only proves anything as
        # an addition to the plain burst above (which has one constant address).
        rotating = [
            self.client.post(
                "/authn/email-auth/request-code/",
                {"email": f"forged{i}@example.com"},
                format="json",
                **rotating_forwarded_for(i),
            ).status_code
            for i in range(BURST)
        ]

        self.assertAll(plain, 202)
        self.assertAll(rotating, 202)

    def test_registrations_and_resends_never_429(self, _ses):
        registered = [
            self.client.post(
                "/authn/register/",
                {
                    "email": f"new{i}@example.com",
                    "password": STRONG_PASSWORD,
                    "password_confirm": STRONG_PASSWORD,
                    "first_name": "New",
                    "last_name": "Student",
                    "organization": "Individual",
                },
                format="json",
            ).status_code
            for i in range(BURST)
        ]
        # A different pending registration per resend: repeating one would (rightly) meet that destination's own cap.
        for i in range(BURST):
            pending = Member.objects.create_user(password=None, is_active=False, registration_pending=True)
            ContactEmail.objects.create(
                member=pending, email_address=f"pending{i}@example.com", email_type="primary", verified=False
            )
        resent = [
            self.client.post(
                "/authn/register/resend-code/", {"email": f"pending{i}@example.com"}, format="json"
            ).status_code
            for i in range(BURST)
        ]

        self.assertAll(registered, 202)
        self.assertAll(resent, 202)

    def test_password_reset_by_email_never_429(self, _ses):
        statuses = [
            self.client.post(
                "/authn/password-reset/request-code/", {"email": f"reset{i}@example.com"}, format="json"
            ).status_code
            for i in range(BURST)
        ]

        self.assertAll(statuses, 202)


@patch(SEND_VIA_PROVIDER, return_value=True)
class DestinationLimitsStillApplyTests(NoIpThrottleTestCase):
    """The per-destination cooldown and hourly cap are the real bound on email sends, whatever the client IP says."""

    URL = "/authn/login/request-code/"

    def request_code(self, email, **extra):
        return self.client.post(self.URL, {"email": email}, format="json", **extra)

    @override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=60)
    def test_same_destination_hits_the_cooldown_even_with_a_rotating_forwarded_for(self, _ses):
        make_member("member@example.com")

        first = self.request_code("member@example.com", **rotating_forwarded_for(1))
        again = [self.request_code("member@example.com", **rotating_forwarded_for(i)) for i in range(2, 6)]
        other_destination = self.request_code("someone-else@example.com", **rotating_forwarded_for(1))

        self.assertEqual(first.status_code, 202)
        self.assertEqual([response.status_code for response in again], [429] * 4)
        self.assertEqual({response.data["code"] for response in again}, {"send_throttled"})
        self.assertTrue(all(response["Retry-After"] for response in again))
        self.assertEqual(other_destination.status_code, 202)

    @override_settings(SEND_VERIFICATION_DESTINATION_HOURLY_LIMIT=3)
    def test_same_destination_hits_the_hourly_cap_while_other_destinations_are_unaffected(self, _ses):
        same = [self.request_code("capped@example.com").status_code for _ in range(5)]
        others = [self.request_code(f"free{i}@example.com").status_code for i in range(BURST)]

        self.assertEqual(same, [202, 202, 202, 429, 429])
        self.assertAll(others, 202)
