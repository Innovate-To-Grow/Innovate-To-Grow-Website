"""Sign-in, email-link, verification-code and ALTCHA flows are not limited per client IP.

Most legitimate users (the campus network) share one public IP, so a per-IP bucket throttles everyone at once while a
rotating ``X-Forwarded-For`` barely slows an attacker. Every burst below is larger than the limit the endpoint used to
have and comes from a single client IP; none may produce a 429. What must still hold: the per-destination cooldown and
hourly cap, and on the SMS request endpoints the global SMS daily budget, with their per-IP throttle kept only as the
fallback while no budget is configured.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, ImpersonationToken
from apps.authn.services import PhoneVerificationInvalid
from apps.mail.models import LoginLinkToken

Member = get_user_model()

# The old limits were 10/min (login), 30/min (challenge issuance, code requests) and 60/min (verify, status lookup),
# each per IP. A burst past each of them from one address must go through untouched.
BURST = 40
LONG_BURST = 70

CHALLENGE_URL = "/authn/send-verification/challenge/"
# Everything up to the provider runs for real; only the SES call is replaced.
SEND_VIA_PROVIDER = "apps.authn.services.email.send_email._send_via_ses"
STRONG_PASSWORD = "StrongPass123!"


def rotating_forwarded_for(index):
    """A different forged ``X-Forwarded-For`` on every request (what defeated the old per-IP key)."""
    return {"HTTP_X_FORWARDED_FOR": f"203.0.113.{index % 250 + 1}, 10.0.0.{index % 250 + 1}"}


def make_member(email, password=None):
    # Most bursts never check a password; skipping the hash keeps forty members cheap to create.
    member = Member.objects.create_user(password=password, is_active=True)
    ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
    return member


class NoIpThrottleTestCase(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()

    def assertAll(self, statuses, expected):
        """Every request got ``expected`` (so in particular none was throttled)."""
        self.assertNotIn(429, statuses)
        self.assertEqual(set(statuses), {expected}, statuses)


class LinkExchangeBurstTests(NoIpThrottleTestCase):
    """Login links and impersonation tokens: the token is the control, not the caller's IP."""

    def test_valid_login_links_from_one_ip_all_log_in_on_both_urls(self):
        for tag, url in (("login", "/mail/login-link/"), ("magic", "/mail/magic-login/")):
            with self.subTest(url=url):
                links = [
                    LoginLinkToken.objects.create(
                        member=make_member(f"{tag}{index}@example.com"), token=LoginLinkToken.generate_token()
                    )
                    for index in range(BURST)
                ]

                statuses = [self.client.post(url, {"token": link.token}, format="json").status_code for link in links]

                self.assertAll(statuses, 200)
                self.assertEqual(
                    LoginLinkToken.objects.filter(pk__in=[link.pk for link in links], is_used=True).count(), BURST
                )

    def test_unknown_login_link_tokens_are_400_never_429_whatever_the_forwarded_for(self):
        plain = [
            self.client.post("/mail/login-link/", {"token": f"plain-{i}"}, format="json").status_code
            for i in range(LONG_BURST)
        ]
        rotating = [
            self.client.post(
                "/mail/login-link/", {"token": f"rotating-{i}"}, format="json", **rotating_forwarded_for(i)
            ).status_code
            for i in range(LONG_BURST)
        ]
        pinned = [
            self.client.post(
                "/mail/login-link/", {"token": f"pinned-{i}"}, format="json", HTTP_X_FORWARDED_FOR="198.51.100.9"
            ).status_code
            for i in range(LONG_BURST)
        ]

        self.assertAll(plain, 400)
        self.assertAll(rotating, 400)
        self.assertAll(pinned, 400)

    def test_impersonation_tokens_from_one_ip_all_log_in(self):
        admin = Member.objects.create_superuser(password="AdminPass123!", first_name="Admin", last_name="User")
        tokens = [
            ImpersonationToken.objects.create(
                member=make_member(f"target{index}@example.com"),
                created_by=admin,
                token=ImpersonationToken.generate_token(),
            )
            for index in range(BURST)
        ]

        statuses = [
            self.client.post("/authn/impersonate-login/", {"token": token.token}, format="json").status_code
            for token in tokens
        ]

        self.assertAll(statuses, 200)

    def test_exchange_bursts_no_longer_starve_password_login(self):
        """The exchange views used to share the password login's bucket (10/min per IP)."""
        make_member("student@example.com", password=STRONG_PASSWORD)
        for index in range(BURST):
            self.client.post("/mail/login-link/", {"token": f"unknown-{index}"}, format="json")
            self.client.post("/authn/impersonate-login/", {"token": f"unknown-{index}"}, format="json")

        response = self.client.post(
            "/authn/login/", {"email": "student@example.com", "password": STRONG_PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, 200)


class VerifyCodeBurstTests(NoIpThrottleTestCase):
    """Code verification is bounded per challenge (attempt cap), never per IP."""

    EMAIL_VERIFY_REQUESTS = (
        ("/authn/login/verify-code/", {"email": "nobody@example.com", "code": "000000"}),
        ("/authn/email-auth/verify-code/", {"email": "nobody@example.com", "code": "000000"}),
        ("/authn/register/verify-code/", {"email": "nobody@example.com", "code": "000000"}),
        ("/authn/password-reset/verify-code/", {"email": "nobody@example.com", "code": "000000"}),
        (
            "/authn/password-reset/confirm/",
            {"email": "nobody@example.com", "verification_token": "x" * 40, "new_password": "NewPass123!"},
        ),
    )

    def test_public_email_verify_endpoints_never_429(self):
        for url, body in self.EMAIL_VERIFY_REQUESTS:
            with self.subTest(url=url):
                statuses = [self.client.post(url, body, format="json").status_code for _ in range(LONG_BURST)]

                self.assertAll(statuses, 400)

    def test_public_email_verify_endpoints_never_429_whatever_the_forwarded_for(self):
        for url, body in self.EMAIL_VERIFY_REQUESTS:
            with self.subTest(url=url):
                rotating = [
                    self.client.post(url, body, format="json", **rotating_forwarded_for(i)).status_code
                    for i in range(LONG_BURST)
                ]
                pinned = [
                    self.client.post(url, body, format="json", HTTP_X_FORWARDED_FOR="198.51.100.9").status_code
                    for _ in range(LONG_BURST)
                ]

                self.assertAll(rotating, 400)
                self.assertAll(pinned, 400)

    @patch("apps.authn.views.auth.codes.phone_code.check_phone_verification", side_effect=PhoneVerificationInvalid())
    def test_phone_verify_endpoint_never_429(self, _check):
        statuses = [
            self.client.post(
                "/authn/phone-auth/verify-code/", {"phone_number": "2025550123", "code": "000000"}, format="json"
            ).status_code
            for _ in range(LONG_BURST)
        ]

        self.assertAll(statuses, 400)
