from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import (
    PhoneVerificationChallenge,
    SendDestinationState,
    SendVerificationChallenge,
    SendVerificationRequest,
)
from apps.authn.services.send_verification.rules.constants import OP_PHONE_AUTH_REQUEST_CODE
from apps.authn.tests.api.send_verification.test_sms_daily_budget import (
    BUDGET,
    BUDGET_SPENT_ANSWER,
    PHONE_AUTH_URL,
    PHONE_AUTH_VERIFY_URL,
    QUOTA_LOGGER,
    SmsBudgetTestCase,
    e164,
)
from apps.authn.tests.helpers.send_verification import mint_send_verification
from apps.authn.tests.helpers.sms_provider import SMS_CODE, sms_budget_used
from apps.event.tests.helpers import make_event


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
        with patch("apps.authn.services.send_verification.guard.quotas._sms_budget_spent", return_value=False):
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

        with patch("apps.authn.services.send_verification.guard.quotas._sms_budget_spent", return_value=False):
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

        with patch("apps.authn.services.send_verification.guard.quotas._sms_budget_spent", return_value=False):
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
