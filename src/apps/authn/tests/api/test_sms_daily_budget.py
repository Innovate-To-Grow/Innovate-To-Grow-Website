"""The global SMS daily budget counts SMS handed to the provider, and nothing else.

A campus shares one public IP, so SMS spend is bounded by one global daily budget instead of a per-IP limit. That
budget must not be drainable for free: a request that sends no SMS (a password reset for a number without an account,
a number over its own hourly cap) reserves nothing. And it must not leak: a password reset answers the same for a
number with and without an account whatever the budget's state, while the flows that always send keep a truthful 429.

The real guard and the real SMS service run here; only the provider call is replaced (``patch_sms_provider``).
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.authn.constants import VERIFICATION_INVALID, VERIFICATION_THROTTLED
from apps.authn.models import (
    ContactPhone,
    PhoneVerificationChallenge,
    SendDestinationState,
    SendQuotaWindow,
    SendVerificationChallenge,
    SendVerificationRequest,
)
from apps.authn.services.send_verification.constants import OP_PHONE_AUTH_REQUEST_CODE
from apps.authn.services.sms import PhoneVerificationDeliveryError
from apps.authn.services.sms.sns_verify import MAX_SENDS_PER_HOUR
from apps.authn.tests.send_verification import mint_send_verification
from apps.authn.tests.sms_provider import SMS_CODE, WRONG_CODE, patch_sms_provider, sms_budget_used
from apps.event.tests.helpers import make_event

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
            "apps.authn.services.send_verification.quotas._day_window_start", side_effect=lambda _now: BUDGET_DAY
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


class PasswordResetAnswerIsBudgetBlindTests(SmsBudgetTestCase):
    """(ii) A reset answers the same for a number with and without an account in every budget state."""

    KNOWN = "2025550100"
    UNKNOWN = "2025550199"

    def setUp(self):
        super().setUp()
        self.phone_member(self.KNOWN)

    def comparable(self, response):
        """Everything a caller can see, with the per-request opaque id replaced by a check that it is one."""
        body = dict(response.data)
        uuid.UUID(str(body.pop("challenge_id")))
        return response.status_code, body, dict(response.headers.items()), sorted(response.cookies.keys())

    def ask_both(self):
        """A reset for the known and the unknown number, each from its own fresh client; then a wrong guess."""
        answers, guesses = {}, {}
        for national in (self.KNOWN, self.UNKNOWN):
            client = APIClient()
            answers[national] = self.reset(national, client)
            guesses[national] = client.post(
                RESET_VERIFY_URL,
                {"identifier": national, "challenge_id": answers[national].data["challenge_id"], "code": WRONG_CODE},
                format="json",
            )
        return answers, guesses

    def assert_indistinguishable(self, answers, guesses):
        self.assertEqual(answers[self.KNOWN].status_code, 202)
        self.assertEqual(self.comparable(answers[self.KNOWN]), self.comparable(answers[self.UNKNOWN]))
        for guess in guesses.values():
            self.assertEqual((guess.status_code, guess.data), (400, {"detail": [VERIFICATION_INVALID]}))
        self.assertEqual(dict(guesses[self.KNOWN].headers.items()), dict(guesses[self.UNKNOWN].headers.items()))

    def test_budget_available(self):
        answers, guesses = self.ask_both()

        self.assert_indistinguishable(answers, guesses)
        self.publish.assert_called_once()  # the account's number got its SMS
        self.assertEqual(sms_budget_used(), 1)

    def test_budget_spent(self):
        self.spend_budget()

        with self.assertLogs(QUOTA_LOGGER, level="INFO") as logs:
            answers, guesses = self.ask_both()

        self.assert_indistinguishable(answers, guesses)
        self.publish.assert_not_called()  # neutral answer, nothing sent, nothing reserved
        self.assertEqual(sms_budget_used(), BUDGET)
        self.assertFalse(PhoneVerificationChallenge.objects.exists())
        # The operator still sees it: exactly one budget line, for the number that would have been sent to.
        self.assertEqual(sum("send_verification.quota_sms_daily" in line for line in logs.output), 1)

    def test_a_dropped_reset_sms_is_recorded_as_the_neutral_answer_it_gave(self):
        """The stored outcome is the neutral 202 too (not a 429 that only the public projection hides)."""
        self.spend_budget()

        with self.assertLogs("apps.authn.serializers.email_code.passwords", level="WARNING") as logs:
            response = self.reset(self.KNOWN)

        record = SendVerificationRequest.objects.get(destination_normalized=e164(self.KNOWN))
        self.assertEqual((record.status, record.http_status, record.client_error_code), ("definitely_failed", 202, ""))
        self.assertEqual(sorted(record.result_payload), ["challenge_id", "message", "status"])
        self.assertEqual(response.data["message"], record.result_payload["message"])
        self.assertIn("Password-reset delivery did not complete", logs.output[0])

    def test_last_unit_then_spent(self):
        self.spend_budget(BUDGET - 1)

        first = self.ask_both()
        cache.clear()
        second = self.ask_both()

        self.assert_indistinguishable(*first)
        self.assert_indistinguishable(*second)
        self.assertEqual(self.comparable(first[0][self.KNOWN]), self.comparable(second[0][self.KNOWN]))
        self.publish.assert_called_once()
        self.assertEqual(sms_budget_used(), BUDGET)

    @override_settings(SEND_VERIFICATION_MODE="observe", SEND_VERIFICATION_TEST_AUTOSOLVE=False)
    def test_budget_spent_in_observe_mode_without_a_proof(self):
        self.spend_budget()

        answers, guesses = self.ask_both()

        self.assert_indistinguishable(answers, guesses)
        self.publish.assert_not_called()

    @override_settings(
        SEND_VERIFICATION_SMS_DAILY_LIMIT=None, SEND_VERIFICATION_MODE="observe", SEND_VERIFICATION_TEST_AUTOSOLVE=False
    )
    def test_no_budget_configured(self):
        answers, guesses = self.ask_both()

        self.assert_indistinguishable(answers, guesses)
        self.publish.assert_called_once()
        self.assertFalse(SendQuotaWindow.objects.exists())

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None)
    def test_enforce_mode_without_a_budget_refuses_both_the_same_way(self):
        answers = {national: self.reset(national, APIClient()) for national in (self.KNOWN, self.UNKNOWN)}

        self.assertEqual(answers[self.KNOWN].status_code, 503)
        self.assertEqual(answers[self.KNOWN].data, answers[self.UNKNOWN].data)
        self.assertEqual(dict(answers[self.KNOWN].headers.items()), dict(answers[self.UNKNOWN].headers.items()))
        self.publish.assert_not_called()

    def test_a_spent_budget_never_answers_a_reset_with_429(self):
        self.spend_budget()

        statuses = [self.reset(self.KNOWN).status_code for _ in range(4)]

        self.assertEqual(statuses, [202] * 4)
        self.publish.assert_not_called()


@override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=60)
class PerDestinationLimitsStillApplyToEveryResetTests(SmsBudgetTestCase):
    """(iii) The cooldown is reserved for every request, account or not, whatever the budget's state."""

    KNOWN = "2025550100"
    UNKNOWN = "2025550199"

    def setUp(self):
        super().setUp()
        self.phone_member(self.KNOWN)

    def assert_second_request_waits(self, national):
        first, second = self.reset(national), self.reset(national)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.data["code"], "send_throttled")
        self.assertEqual(second.data["detail"], "Please wait before requesting another code.")
        self.assertIn(second.data["retry_after"], range(1, 62))
        self.assertEqual(second["Retry-After"], str(second.data["retry_after"]))
        return second

    def test_cooldown_applies_to_numbers_with_and_without_an_account(self):
        known, unknown = (self.assert_second_request_waits(national) for national in (self.KNOWN, self.UNKNOWN))

        self.assertEqual(sorted(known.data), sorted(unknown.data))
        self.publish.assert_called_once()
        self.assertEqual(sms_budget_used(), 1)  # the refused second request reserved nothing
        self.assertEqual(SendDestinationState.objects.count(), 2)

    def test_cooldown_applies_while_the_budget_is_spent(self):
        self.spend_budget()

        for national in (self.KNOWN, self.UNKNOWN):
            with self.subTest(national=national):
                self.assert_second_request_waits(national)
        self.publish.assert_not_called()

    def test_phone_auth_keeps_its_cooldown_too(self):
        first, second = self.phone_auth("2025550150"), self.phone_auth("2025550150")

        self.assertEqual((first.status_code, second.status_code), (202, 429))
        self.assertEqual(second.data["detail"], "Please wait before requesting another code.")
        self.assertEqual(sms_budget_used(), 1)


class FlowsThatAlwaysSendKeepTheirTruthful429Tests(SmsBudgetTestCase):
    """(iv) Where any number receives an SMS, a spent budget is answered as what it is."""

    def test_phone_auth_is_refused_before_anything_is_used(self):
        self.spend_budget()

        with self.assertLogs(QUOTA_LOGGER, level="INFO") as logs:
            response = self.phone_auth("2025550150")

        self.assert_budget_spent_answer(response)
        self.publish.assert_not_called()
        self.assertTrue(any("send_verification.quota_sms_daily" in line for line in logs.output))
        # Refused in the reservation transaction, which rolled back: the proof is still unused, no cooldown is set
        # and no request row was written.
        self.assertEqual(SendVerificationChallenge.objects.get().status, SendVerificationChallenge.Status.PENDING)
        self.assertFalse(SendVerificationRequest.objects.exists())
        self.assertFalse(SendDestinationState.objects.exists())
        self.assertFalse(PhoneVerificationChallenge.objects.exists())
        self.assertEqual(sms_budget_used(), BUDGET)

    @override_settings(SEND_VERIFICATION_MODE="observe", SEND_VERIFICATION_TEST_AUTOSOLVE=False)
    def test_phone_auth_without_a_proof_in_observe_mode_gets_the_same_answer(self):
        self.spend_budget()

        self.assert_budget_spent_answer(self.phone_auth("2025550150"))
        self.publish.assert_not_called()

    def test_phone_auth_burst_sends_exactly_the_budget(self):
        responses = [self.phone_auth(f"20255503{index:02d}") for index in range(BUDGET + 2)]

        self.assertEqual([response.status_code for response in responses], [202] * BUDGET + [429] * 2)
        for response in responses[BUDGET:]:
            self.assert_budget_spent_answer(response)
        self.assertEqual(self.publish.call_count, BUDGET)
        self.assertEqual(sms_budget_used(), BUDGET)

    def test_losing_the_race_for_the_last_unit_gets_the_same_answer_at_dispatch(self):
        """Two requests pass the early check with one unit left; the reservation at dispatch decides."""
        self.spend_budget(BUDGET - 1)
        winner = self.phone_auth("2025550150")
        proof = mint_send_verification(self.client, OP_PHONE_AUTH_REQUEST_CODE, {"phone_number": "2025550151"})

        # The early check ran before the winner's reservation committed, so it still saw a unit.
        with patch("apps.authn.services.send_verification.quotas._sms_budget_spent", return_value=False):
            loser = self.client.post(PHONE_AUTH_URL, {"phone_number": "2025550151", **proof}, format="json")
            replay = self.client.post(PHONE_AUTH_URL, {"phone_number": "2025550151", **proof}, format="json")

        self.assertEqual(winner.status_code, 202)
        self.assert_budget_spent_answer(loser)
        self.assert_budget_spent_answer(replay)  # a transport retry replays the recorded answer, header included
        self.publish.assert_called_once()
        self.assertEqual(sms_budget_used(), BUDGET)
        self.assertFalse(PhoneVerificationChallenge.objects.filter(phone_number=e164("2025550151")).exists())
        record = SendVerificationRequest.objects.get(request_id=proof["send_request_id"])
        self.assertEqual(
            (record.status, record.http_status, record.client_error_code), ("definitely_failed", 429, "send_throttled")
        )
        status = self.client.get(f"/authn/send-verification/requests/{proof['send_request_id']}/")
        self.assertEqual((status.data["status"], status.data["http_status"]), ("definitely_failed", 429))
        self.assertEqual(status.data["result"], BUDGET_SPENT_ANSWER)

    def test_a_refusal_at_dispatch_leaves_the_code_already_sent_valid(self):
        self.spend_budget(BUDGET - 1)
        first = self.phone_auth("2025550150")

        with patch("apps.authn.services.send_verification.quotas._sms_budget_spent", return_value=False):
            second = self.phone_auth("2025550150")

        self.assert_budget_spent_answer(second)
        challenge = PhoneVerificationChallenge.objects.get()  # the refused request stored nothing
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.PENDING)
        verified = self.client.post(
            PHONE_AUTH_VERIFY_URL,
            {"phone_number": "2025550150", "challenge_id": first.data["challenge_id"], "code": SMS_CODE},
            format="json",
        )
        self.assertEqual(verified.status_code, 200, verified.data)

    def authenticated_sms_requests(self):
        phone_only, _phone = self.phone_member("2025550100")
        owner, unverified = self.phone_member("2025550101", verified=False)
        event = make_event(registration_open=True, collect_phone=True, verify_phone=True)
        return (
            ("change password by SMS", phone_only, "/authn/change-password/request-code/", {}),
            ("contact phone", owner, f"/authn/contact-phones/{unverified.pk}/request-verification/", {}),
            ("event phone code", owner, "/event/send-phone-code/", {"phone": "2025550102", "event_slug": event.slug}),
        )

    def test_the_authenticated_sms_flows_answer_the_same_429(self):
        self.spend_budget()

        for name, member, url, payload in self.authenticated_sms_requests():
            with self.subTest(flow=name):
                self.client.force_authenticate(member)
                self.assert_budget_spent_answer(self.client.post(url, payload, format="json"))
        self.publish.assert_not_called()
        self.assertEqual(sms_budget_used(), BUDGET)
        self.assertFalse(SendVerificationRequest.objects.exists())

    def test_the_authenticated_sms_flows_answer_the_same_429_when_refused_at_dispatch(self):
        """None of their views turns the dispatch-time refusal into another answer (a 503, a generic 400)."""
        self.spend_budget()

        with patch("apps.authn.services.send_verification.quotas._sms_budget_spent", return_value=False):
            for name, member, url, payload in self.authenticated_sms_requests():
                with self.subTest(flow=name):
                    self.client.force_authenticate(member)
                    self.assert_budget_spent_answer(self.client.post(url, payload, format="json"))
        self.publish.assert_not_called()
        self.assertEqual(sms_budget_used(), BUDGET)
        self.assertFalse(PhoneVerificationChallenge.objects.exists())
        self.assertEqual(
            set(SendVerificationRequest.objects.values_list("status", "http_status")), {("definitely_failed", 429)}
        )
