import uuid

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.authn.constants import VERIFICATION_INVALID
from apps.authn.models import (
    PhoneVerificationChallenge,
    SendDestinationState,
    SendQuotaWindow,
    SendVerificationRequest,
)
from apps.authn.tests.api.send_verification.test_sms_daily_budget import (
    BUDGET,
    QUOTA_LOGGER,
    RESET_VERIFY_URL,
    SmsBudgetTestCase,
    e164,
)
from apps.authn.tests.helpers.sms_provider import WRONG_CODE, sms_budget_used


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

        with self.assertLogs("apps.authn.serializers.email_code.password_reset_request", level="WARNING") as logs:
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
