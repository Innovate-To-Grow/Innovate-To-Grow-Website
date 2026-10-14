"""Sign-in, email-link, verification-code and ALTCHA flows are not limited per client IP.

Most legitimate users (the campus network) share one public IP, so a per-IP bucket throttles everyone at once while a
rotating ``X-Forwarded-For`` barely slows an attacker. Every burst below is larger than the limit the endpoint used to
have and comes from a single client IP; none may produce a 429. What must still hold: the per-destination cooldown and
hourly cap, and on the SMS request endpoints the global SMS daily budget, with their per-IP throttle kept only as the
fallback while no budget is configured.
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, ContactPhone, ImpersonationToken, SendQuotaWindow
from apps.authn.security.throttles import PhoneAuthCodeRequestThrottle, sms_request_throttles
from apps.authn.services import PhoneVerificationInvalid
from apps.authn.tests.sms_provider import patch_sms_provider
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

    @patch("apps.authn.views.auth.phone_code.check_phone_verification", side_effect=PhoneVerificationInvalid())
    def test_phone_verify_endpoint_never_429(self, _check):
        statuses = [
            self.client.post(
                "/authn/phone-auth/verify-code/", {"phone_number": "2025550123", "code": "000000"}, format="json"
            ).status_code
            for _ in range(LONG_BURST)
        ]

        self.assertAll(statuses, 400)


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
            pending = Member.objects.create_user(password=None, is_active=False)
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


# Local and test settings configure a daily SMS budget; the fallback only exists without one. Observe mode, because
# enforce mode refuses every SMS until a budget is configured (``require_ready``), before the throttle could matter.
@override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None, SEND_VERIFICATION_MODE="observe")
class SmsFallbackThrottleTests(NoIpThrottleTestCase):
    """No SMS daily budget configured: the per-IP SMS throttle is the only aggregate bound left, so it applies."""

    @patch("apps.authn.services.sms.start_phone_verification", return_value="pending")
    def test_passwordless_phone_request_is_still_throttled_at_five_per_minute(self, _start):
        statuses = [
            self.client.post(
                "/authn/phone-auth/request-code/", {"phone_number": "2025550123"}, format="json"
            ).status_code
            for _ in range(7)
        ]

        self.assertEqual(statuses, [202] * 5 + [429] * 2)

    @patch("apps.authn.services.sms.start_phone_verification", return_value="pending")
    def test_password_reset_by_phone_is_still_throttled_at_five_per_minute(self, _start):
        statuses = [
            self.client.post(
                "/authn/password-reset/request-code/", {"identifier": "2025550123"}, format="json"
            ).status_code
            for _ in range(7)
        ]

        self.assertEqual(statuses, [202] * 5 + [429] * 2)

    # Observe mode: the request needs no ALTCHA proof. The test-mode autosolver derives its destination from the raw
    # ``identifier`` (untrimmed), so it cannot follow the blank-alias payloads below; the throttle is independent of it.
    @override_settings(SEND_VERIFICATION_MODE="observe")
    @patch("apps.authn.services.sms.start_phone_verification", return_value="pending")
    def test_password_reset_by_phone_cannot_dodge_the_sms_throttle_with_a_blank_identifier(self, _start):
        """The serializer trims each field and falls back from ``identifier`` to ``email``; the throttle must agree.

        A blank ``identifier`` plus a phone number in the legacy ``email`` alias is a phone request to the serializer
        (a real SMS is sent), so it must still be counted against the SMS throttle.
        """
        payloads = (
            {"identifier": " ", "email": "2025550123"},
            {"identifier": "\t \n", "email": "2025550123"},
            {"identifier": "", "email": "2025550123"},
            {"email": "  2025550123  "},
            {"identifier": "  2025550123  "},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                cache.clear()
                statuses = [
                    self.client.post("/authn/password-reset/request-code/", payload, format="json").status_code
                    for _ in range(7)
                ]

                self.assertEqual(statuses, [202] * 5 + [429] * 2)

    @override_settings(SEND_VERIFICATION_MODE="observe")
    @patch("apps.authn.services.sms.start_phone_verification", return_value="pending")
    def test_password_reset_email_identifier_is_not_sms_throttled(self, start):
        """The other side of the same decision: a real email address (even with a blank alias) is no SMS request.

        Repeating the SAME address is still answered 429 by the per-destination cooldown, but that is the send guard's
        ``send_throttled`` answer, not DRF's per-IP throttle body, and nothing may reach the SMS provider.
        """
        # A different address per payload: the per-destination hourly cap is database backed (cache.clear() does not
        # reset it) and would otherwise answer the later payloads' first request.
        payloads = (
            {"identifier": " ", "email": "someone-a@example.com"},
            {"identifier": "someone-b@example.com"},
            {"email": "someone-c@example.com"},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                cache.clear()
                responses = [
                    self.client.post("/authn/password-reset/request-code/", payload, format="json") for _ in range(7)
                ]

                self.assertEqual(responses[0].status_code, 202)
                for response in responses:
                    if response.status_code == 429:
                        self.assertEqual(response.data.get("code"), "send_throttled")
                start.assert_not_called()

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT="not-a-number")
    @patch("apps.authn.services.sms.start_phone_verification", return_value="pending")
    def test_unreadable_sms_budget_keeps_the_ip_throttle(self, start):
        """A settings error while reading the budget fails safe: the per-IP throttle stays on."""
        with self.assertLogs("apps.authn.security.throttles", level="WARNING"):
            responses = [
                self.client.post("/authn/phone-auth/request-code/", {"phone_number": "2025550123"}, format="json")
                for _ in range(7)
            ]

        # The guard cannot read its settings either (503), but only the per-IP throttle answers the sixth request on.
        self.assertEqual([response.status_code for response in responses], [503] * 5 + [429] * 2)
        self.assertEqual({response.data["detail"].code for response in responses[5:]}, {"throttled"})
        start.assert_not_called()


@override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=12)
class SmsDailyBudgetReplacesIpThrottleTests(NoIpThrottleTestCase):
    """A configured SMS daily budget bounds spend on its own, so the campus is never limited per IP.

    Real guard and real SMS service, enforce mode, test-mode proofs; only the provider call is replaced. A burst to
    distinct numbers from ONE address (past the 5/minute fallback) goes through until the budget itself answers,
    with its own ``send_throttled`` body. The budget counts SMS handed to the provider and nothing else
    (``test_sms_daily_budget`` covers that in detail).
    """

    BUDGET = 12

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.publish = patch_sms_provider(self)

    def budget_used(self):
        return sum(
            SendQuotaWindow.objects.filter(kind=SendQuotaWindow.Kind.SMS_DAILY).values_list("reserved_count", flat=True)
        )

    def assert_budget_answer(self, responses):
        for response in responses:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "send_throttled")
            self.assertEqual(response.data["detail"], "The SMS sending budget for today has been reached.")

    def test_campus_phone_auth_burst_is_stopped_only_by_the_daily_budget(self):
        responses = [
            self.client.post("/authn/phone-auth/request-code/", {"phone_number": f"20255501{i:02d}"}, format="json")
            for i in range(self.BUDGET + 2)
        ]

        self.assertEqual([response.status_code for response in responses], [202] * self.BUDGET + [429] * 2)
        self.assert_budget_answer(responses[self.BUDGET :])
        self.assertEqual(self.publish.call_count, self.BUDGET)
        self.assertEqual(self.budget_used(), self.BUDGET)

    def test_campus_password_reset_burst_for_numbers_without_an_account_is_never_stopped(self):
        """No SMS is sent for a number without an account, so such requests cannot use the budget up."""
        responses = [
            self.client.post("/authn/password-reset/request-code/", {"identifier": f"20255502{i:02d}"}, format="json")
            for i in range(self.BUDGET + 2)
        ]

        self.assertAll([response.status_code for response in responses], 202)
        self.publish.assert_not_called()
        self.assertEqual(self.budget_used(), 0)

    def test_the_budget_is_shared_by_both_sms_endpoints(self):
        """One global budget: the SMS both public endpoints send draw from the same daily reservation."""
        half = self.BUDGET // 2
        for i in range(half + 1):
            member = Member.objects.create_user(password=None, is_active=True)
            ContactPhone.objects.create(member=member, phone_number=f"20255504{i:02d}", region="1-US", verified=True)

        phone_auth = [
            self.client.post("/authn/phone-auth/request-code/", {"phone_number": f"20255503{i:02d}"}, format="json")
            for i in range(half)
        ]
        resets = [
            self.client.post("/authn/password-reset/request-code/", {"identifier": f"20255504{i:02d}"}, format="json")
            for i in range(half + 1)
        ]
        late = self.client.post("/authn/phone-auth/request-code/", {"phone_number": "2025550399"}, format="json")

        self.assertEqual([response.status_code for response in phone_auth], [202] * half)
        # A reset never answers with the budget: the last one is the usual neutral 202, and its SMS is not sent.
        self.assertEqual([response.status_code for response in resets], [202] * (half + 1))
        self.assertEqual(self.publish.call_count, self.BUDGET)
        self.assertEqual(self.budget_used(), self.BUDGET)
        self.assert_budget_answer([late])


class SmsThrottleSelectionTests(NoIpThrottleTestCase):
    """``sms_request_throttles`` itself: the per-IP throttle exactly when no budget can be read."""

    def assert_ip_throttled(self, throttles):
        self.assertEqual([type(throttle) for throttle in throttles], [PhoneAuthCodeRequestThrottle])

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=500)
    def test_a_budget_from_settings_removes_the_ip_throttle(self):
        self.assertEqual(sms_request_throttles(), [])

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None)
    def test_a_budget_from_the_active_database_config_removes_the_ip_throttle(self):
        from apps.core.models import SendVerificationConfig

        config = SendVerificationConfig.objects.create(name="Production", is_active=True, sms_daily_limit=300)
        self.assertEqual(sms_request_throttles(), [])

        config.sms_daily_limit = None
        config.save()
        self.assert_ip_throttled(sms_request_throttles())

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=0)
    def test_a_cleared_budget_keeps_the_ip_throttle(self):
        # Zero explicitly clears the cap (``load_settings``); it never means an unlimited budget.
        self.assert_ip_throttled(sms_request_throttles())

    def test_any_failure_to_read_the_budget_keeps_the_ip_throttle(self):
        with (
            patch(
                "apps.authn.services.send_verification.config.load_settings", side_effect=RuntimeError("database down")
            ),
            self.assertLogs("apps.authn.security.throttles", level="WARNING") as logs,
        ):
            throttles = sms_request_throttles()

        self.assert_ip_throttled(throttles)
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("database down", logs.output[0])
