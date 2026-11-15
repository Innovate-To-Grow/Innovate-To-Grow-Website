from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from apps.authn.models import ContactPhone, SendQuotaWindow
from apps.authn.tests.api.limits.degradation.test_no_ip_throttle import Member, NoIpThrottleTestCase
from apps.authn.tests.helpers.sms_provider import patch_sms_provider


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
