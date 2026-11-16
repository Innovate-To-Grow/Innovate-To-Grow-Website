"""The global SMS daily budget counts SMS handed to the provider, and nothing else.

A campus shares one public IP, so SMS spend is bounded by one global daily budget instead of a per-IP limit. That
budget must not be drainable for free: a request that sends no SMS (a password reset for a number without an account,
a number over its own hourly cap) reserves nothing. And it must not leak: a password reset answers the same for a
number with and without an account whatever the budget's state, while the flows that always send keep a truthful 429.

The real guard and the real SMS service run here; only the provider call is replaced (``patch_sms_provider``).
"""

from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.constants import VERIFICATION_THROTTLED
from apps.authn.models import (
    ContactPhone,
    PhoneVerificationChallenge,
    SendQuotaWindow,
)
from apps.authn.services.sms import PhoneVerificationDeliveryError
from apps.authn.services.sms.sns_verify import MAX_SENDS_PER_HOUR
from apps.authn.tests.helpers.sms_provider import SMS_CODE, patch_sms_provider, sms_budget_used

Member = get_user_model()

RESET_URL = "/authn/password-reset/request-code/"
RESET_VERIFY_URL = "/authn/password-reset/verify-code/"
PHONE_AUTH_URL = "/authn/phone-auth/request-code/"
PHONE_AUTH_VERIFY_URL = "/authn/phone-auth/verify-code/"

QUOTA_LOGGER = "apps.authn.send_verification"
BUDGET = 3
BUDGET_SPENT_ANSWER = {
    "code": "send_throttled",
    "detail": "The SMS sending budget for today has been reached.",
    "retry_after": 3600,
}
# The budget window is the UTC day. Pinning it keeps a run that straddles midnight from changing windows mid-test.
BUDGET_DAY = datetime(2026, 9, 30, tzinfo=UTC)


def e164(national: str) -> str:
    return f"+1{national}"


@override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=BUDGET)
class SmsBudgetTestCase(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.publish = patch_sms_provider(self)
        patcher = patch(
            "apps.authn.services.send_verification.guard.quotas._day_window_start", side_effect=lambda _now: BUDGET_DAY
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def phone_member(national, *, verified=True):
        member = Member.objects.create_user(password=None, is_active=True)
        phone = ContactPhone.objects.create(member=member, phone_number=national, region="1-US", verified=verified)
        return member, phone

    @staticmethod
    def spend_budget(units=BUDGET):
        SendQuotaWindow.objects.update_or_create(
            kind=SendQuotaWindow.Kind.SMS_DAILY,
            scope_key="sms:global",
            window_started_at=BUDGET_DAY,
            defaults={"reserved_count": units},
        )

    def reset(self, national, client=None):
        return (client or self.client).post(RESET_URL, {"identifier": national}, format="json")

    def phone_auth(self, national, client=None):
        return (client or self.client).post(PHONE_AUTH_URL, {"phone_number": national}, format="json")

    def assert_budget_spent_answer(self, response):
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data, BUDGET_SPENT_ANSWER)
        self.assertEqual(response["Retry-After"], "3600")


class BudgetCountsDispatchedSmsOnlyTests(SmsBudgetTestCase):
    """(i) One unit per SMS handed to the provider; a request that sends nothing reserves nothing."""

    # No proof is needed in observe mode, which made this free: before the fix, BUDGET such requests stopped every
    # SMS code for the whole campus until the UTC day ended.
    @override_settings(SEND_VERIFICATION_MODE="observe", SEND_VERIFICATION_TEST_AUTOSOLVE=False)
    def test_resets_for_unknown_numbers_leave_the_budget_untouched_and_a_real_phone_login_still_works(self):
        responses = [self.reset(f"20255502{index:02d}") for index in range(BUDGET * 7)]

        self.assertEqual({response.status_code for response in responses}, {202})
        self.publish.assert_not_called()
        self.assertEqual(sms_budget_used(), 0)
        self.assertFalse(PhoneVerificationChallenge.objects.exists())

        login = self.phone_auth("2025550150")

        self.assertEqual(login.status_code, 202, login.data)
        self.publish.assert_called_once()
        self.assertEqual(sms_budget_used(), 1)
        verified = self.client.post(
            PHONE_AUTH_VERIFY_URL,
            {"phone_number": "2025550150", "challenge_id": login.data["challenge_id"], "code": SMS_CODE},
            format="json",
        )
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertIn("access", verified.data)

    def test_a_reset_for_a_number_with_an_account_spends_one_unit_per_sms(self):
        self.phone_member("2025550100")

        responses = [self.reset("2025550100") for _ in range(2)]

        self.assertEqual([response.status_code for response in responses], [202, 202])
        self.assertEqual(self.publish.call_count, 2)
        self.assertEqual(sms_budget_used(), 2)

    def test_a_number_over_its_own_hourly_cap_spends_nothing(self):
        self.phone_member("2025550100")
        now = timezone.now()
        PhoneVerificationChallenge.objects.bulk_create(
            PhoneVerificationChallenge(
                phone_number=e164("2025550100"),
                purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
                code_hash=make_password(None),
                status=PhoneVerificationChallenge.Status.EXPIRED,
                expires_at=now,
                send_reserved_at=now,
            )
            for _ in range(MAX_SENDS_PER_HOUR)
        )

        reset = self.reset("2025550100")
        login = self.phone_auth("2025550100")

        self.assertEqual(reset.status_code, 202)
        self.assertEqual((login.status_code, login.data), (429, {"detail": VERIFICATION_THROTTLED}))
        self.publish.assert_not_called()
        self.assertEqual(sms_budget_used(), 0)

    def test_the_unit_is_committed_before_the_provider_is_called(self):
        seen = {}

        def provider(**_kwargs):
            seen["budget"] = sms_budget_used()
            seen["challenge"] = PhoneVerificationChallenge.objects.get().status
            return "provider-message-id"

        self.publish.side_effect = provider

        self.assertEqual(self.phone_auth("2025550150").status_code, 202)

        self.assertEqual(seen, {"budget": 1, "challenge": PhoneVerificationChallenge.Status.SENDING})

    def test_a_failed_or_uncertain_provider_call_keeps_its_unit(self):
        self.publish.side_effect = PhoneVerificationDeliveryError("timeout", outcome="uncertain")
        uncertain = self.phone_auth("2025550150")
        self.publish.side_effect = PhoneVerificationDeliveryError("rejected", outcome="permanent")
        failed = self.phone_auth("2025550151")

        self.assertEqual((uncertain.status_code, uncertain.data["code"]), (409, "send_unknown"))
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(self.publish.call_count, 2)
        self.assertEqual(sms_budget_used(), 2)  # never released: the count can overstate spend, never understate it

    def test_the_budget_equals_the_provider_calls_across_flows(self):
        self.phone_member("2025550100")
        member, phone = self.phone_member("2025550101", verified=False)

        self.assertEqual(self.reset("2025550100").status_code, 202)
        self.assertEqual(self.reset("2025550199").status_code, 202)  # no account: nothing sent
        self.assertEqual(self.phone_auth("2025550150").status_code, 202)
        self.client.force_authenticate(member)
        contact = self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/", {}, format="json")
        self.assertEqual(contact.status_code, 202, contact.data)

        self.assertEqual(self.publish.call_count, 3)
        self.assertEqual(sms_budget_used(), 3)
        self.assertEqual(PhoneVerificationChallenge.objects.count(), 3)
