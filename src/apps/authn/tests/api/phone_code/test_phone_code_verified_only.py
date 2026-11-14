"""Phone sign-in works only for VERIFIED numbers.

A number staff or a spreadsheet import saved on an account was never proven to be the member's (it may be mistyped
or recycled), so holding it must not open the account. Such a number gets a *withheld* code: the request is answered
exactly like a real send (same body, same refusals, same limits, about the same time) but no SMS is sent and no
budget is spent, and the code can never be used. The member verifies the number with a code from the account page;
from then on it signs in.

The real guard and SMS service run here; only the provider call is replaced (``patch_sms_provider``).
"""

from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.authn.constants import VERIFICATION_INVALID, VERIFICATION_THROTTLED
from apps.authn.models import ContactPhone, PhoneVerificationChallenge, SendQuotaWindow, SendVerificationRequest
from apps.authn.services.send_verification import quotas
from apps.authn.services.send_verification.constants import OP_PHONE_AUTH_REQUEST_CODE
from apps.authn.services.sms import PhoneVerificationBusy, PhoneVerificationDeliveryError, latency
from apps.authn.services.sms.sns_verify import MAX_SENDS_PER_HOUR, MAX_VERIFY_ATTEMPTS
from apps.authn.tests.send_verification import mint_send_verification
from apps.authn.tests.sms_provider import SMS_CODE, WRONG_CODE, patch_sms_provider, sms_budget_used

Member = get_user_model()

REQUEST_URL = "/authn/phone-auth/request-code/"
VERIFY_URL = "/authn/phone-auth/verify-code/"
BUDGET = 50
BUDGET_DAY = datetime(2026, 9, 30, tzinfo=UTC)
UNVERIFIED = "2025550101"
UNKNOWN = "2025550199"
VERIFIED = "2025550102"


def e164(national: str) -> str:
    return f"+1{national}"


@override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=BUDGET)
class VerifiedOnlyTestCase(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.publish = patch_sms_provider(self)
        patcher = patch.object(quotas, "_day_window_start", side_effect=lambda _now: BUDGET_DAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        latency.reset()
        self.addCleanup(latency.reset)
        self.staffed = Member.objects.create_user(password=None, is_active=True, first_name="Una", last_name="Ver")
        self.unverified = ContactPhone.objects.create(
            member=self.staffed, phone_number=UNVERIFIED, region="1-US", verified=False
        )
        self.owner = Member.objects.create_user(password=None, is_active=True, first_name="Vera", last_name="Fied")
        ContactPhone.objects.create(member=self.owner, phone_number=VERIFIED, region="1-US", verified=True)

    def request_code(self, national, client=None):
        return (client or self.client).post(REQUEST_URL, {"phone_number": national}, format="json")

    def verify(self, national, challenge_id, code, client=None):
        return (client or self.client).post(
            VERIFY_URL, {"phone_number": national, "challenge_id": challenge_id, "code": code}, format="json"
        )

    def published_to(self):
        return [call.kwargs["phone_number"] for call in self.publish.call_args_list]


class WithheldCodeAnswersLikeARealSendTests(VerifiedOnlyTestCase):
    def test_an_unverified_number_is_answered_like_an_unknown_one_but_nothing_is_sent(self):
        withheld = self.request_code(UNVERIFIED)
        signup = self.request_code(UNKNOWN)
        login = self.request_code(VERIFIED)

        for response in (withheld, signup, login):
            self.assertEqual(response.status_code, 202, response.data)
            self.assertEqual(set(response.data), {"message", "challenge_id"})
            self.assertEqual(response.data["message"], signup.data["message"])
        self.assertEqual(self.published_to(), [e164(UNKNOWN), e164(VERIFIED)])
        self.assertEqual(sms_budget_used(), 2)  # the withheld code spent nothing

        challenge = PhoneVerificationChallenge.objects.get(phone_number=e164(UNVERIFIED))
        self.assertEqual(str(challenge.pk), withheld.data["challenge_id"])
        self.assertEqual(
            (challenge.purpose, challenge.status, challenge.sent_at),
            (PhoneVerificationChallenge.Purpose.PHONE_AUTH, PhoneVerificationChallenge.Status.PENDING, None),
        )
        self.assertIsNotNone(challenge.send_reserved_at)
        sent = PhoneVerificationChallenge.objects.get(phone_number=e164(UNKNOWN))
        self.assertIsNotNone(sent.sent_at)
        self.unverified.refresh_from_db()
        self.assertFalse(self.unverified.verified)

    def test_the_send_request_and_its_status_look_like_a_real_send(self):
        statuses = {}
        for national in (UNVERIFIED, UNKNOWN):
            proof = mint_send_verification(self.client, OP_PHONE_AUTH_REQUEST_CODE, {"phone_number": national})
            response = self.client.post(REQUEST_URL, {"phone_number": national, **proof}, format="json")
            self.assertEqual(response.status_code, 202)
            record = SendVerificationRequest.objects.get(request_id=proof["send_request_id"])
            self.assertEqual(record.otp_challenge_id, response.data["challenge_id"])
            status = self.client.get(f"/authn/send-verification/requests/{proof['send_request_id']}/").data
            statuses[national] = (record.status, record.http_status, status["status"], status["http_status"])
            self.assertEqual(status["challenge_id"], response.data["challenge_id"])
            self.assertEqual(status["result"], response.data)

        self.assertEqual(statuses[UNVERIFIED], statuses[UNKNOWN])
        self.assertEqual(statuses[UNKNOWN], ("provider_accepted", 202, "provider_accepted", 202))

    def test_a_withheld_code_fails_every_guess_exactly_like_a_real_code(self):
        withheld = self.request_code(UNVERIFIED).data["challenge_id"]
        real = self.request_code(UNKNOWN).data["challenge_id"]

        answers = {}
        for national, challenge_id in ((UNVERIFIED, withheld), (UNKNOWN, real)):
            answers[national] = [
                (response.status_code, response.data)
                for response in (self.verify(national, challenge_id, WRONG_CODE) for _ in range(MAX_VERIFY_ATTEMPTS))
            ]

        self.assertEqual(answers[UNVERIFIED], answers[UNKNOWN])
        self.assertEqual(answers[UNKNOWN][0], (400, {"detail": VERIFICATION_INVALID}))
        self.assertEqual(answers[UNKNOWN][-1], (429, {"detail": VERIFICATION_THROTTLED}))

    def test_the_code_a_send_would_have_carried_does_not_open_the_account(self):
        # The provider stub would have sent SMS_CODE; a withheld challenge is hashed from a secret no code equals.
        challenge_id = self.request_code(UNVERIFIED).data["challenge_id"]
        members = Member.objects.count()

        response = self.verify(UNVERIFIED, challenge_id, SMS_CODE)

        self.assertEqual((response.status_code, response.data), (400, {"detail": VERIFICATION_INVALID}))
        self.assertEqual(Member.objects.count(), members)
        self.unverified.refresh_from_db()
        self.assertEqual((self.unverified.member_id, self.unverified.verified), (self.staffed.pk, False))

    def test_the_answer_waits_like_a_provider_call(self):
        latency.observe_send(0.321)
        with patch.object(latency.context, "sleep") as sleep:
            self.assertEqual(self.request_code(UNVERIFIED).status_code, 202)
        sleep.assert_called_once_with(0.321)

    def test_the_delivery_slot_is_given_back(self):
        with patch("apps.authn.services.sms.provider.release") as release:
            self.assertEqual(self.request_code(UNVERIFIED).status_code, 202)
        release.assert_called_once()


class WithheldCodeRefusalsMatchARealSendTests(VerifiedOnlyTestCase):
    def assert_same_answer(self, first, second):
        self.assertEqual((first.status_code, first.data), (second.status_code, second.data))
        self.assertEqual(first.get("Retry-After"), second.get("Retry-After"))

    def test_the_hourly_cap_counts_withheld_codes(self):
        for national in (UNVERIFIED, UNKNOWN):
            answers = [self.request_code(national).status_code for _ in range(MAX_SENDS_PER_HOUR)]
            self.assertEqual(answers, [202] * MAX_SENDS_PER_HOUR)

        self.assert_same_answer(self.request_code(UNVERIFIED), self.request_code(UNKNOWN))
        self.assertEqual(self.request_code(UNVERIFIED).data, {"detail": VERIFICATION_THROTTLED})
        self.assertEqual(self.published_to(), [e164(UNKNOWN)] * MAX_SENDS_PER_HOUR)

    def test_a_spent_budget_answers_the_same(self):
        SendQuotaWindow.objects.create(
            kind=SendQuotaWindow.Kind.SMS_DAILY,
            scope_key="sms:global",
            window_started_at=BUDGET_DAY,
            reserved_count=BUDGET,
        )

        withheld, unknown = self.request_code(UNVERIFIED), self.request_code(UNKNOWN)

        self.assert_same_answer(withheld, unknown)
        self.assertEqual((withheld.status_code, withheld.data["code"]), (429, "send_throttled"))
        self.publish.assert_not_called()

    def test_a_budget_spent_between_the_checks_is_refused_at_dispatch_like_a_send(self):
        # The early check (proof time) still saw a unit; the one at dispatch finds the budget gone.
        SendQuotaWindow.objects.create(
            kind=SendQuotaWindow.Kind.SMS_DAILY,
            scope_key="sms:global",
            window_started_at=BUDGET_DAY,
            reserved_count=BUDGET,
        )
        real_check = quotas._sms_budget_spent
        answers = {}
        for national in (UNVERIFIED, UNKNOWN):
            checks = []

            def budget_spent(*args, checks=checks):
                checks.append(args)
                return False if len(checks) == 1 else real_check(*args)

            with patch.object(quotas, "_sms_budget_spent", side_effect=budget_spent):
                answers[national] = self.request_code(national)

        self.assert_same_answer(answers[UNVERIFIED], answers[UNKNOWN])
        self.assertEqual(answers[UNVERIFIED].status_code, 429)
        self.assertFalse(PhoneVerificationChallenge.objects.exists())  # both reservations rolled back
        self.publish.assert_not_called()

    def test_sms_not_configured_answers_the_same(self):
        with patch(
            "apps.authn.services.sms.sns_verify._assert_configured",
            side_effect=PhoneVerificationDeliveryError("SMS is not configured.", outcome="permanent"),
        ):
            withheld, unknown = self.request_code(UNVERIFIED), self.request_code(UNKNOWN)

        self.assert_same_answer(withheld, unknown)
        self.assertEqual(withheld.status_code, 503)

    def test_held_back_delivery_answers_the_same(self):
        with patch("apps.authn.services.sms.sns_verify._admit_otp", side_effect=PhoneVerificationBusy(7)):
            withheld, unknown = self.request_code(UNVERIFIED), self.request_code(UNKNOWN)

        self.assert_same_answer(withheld, unknown)
        self.assertEqual((withheld.status_code, withheld["Retry-After"]), (503, "7"))
        self.assertFalse(PhoneVerificationChallenge.objects.exists())


class VerifiedNumbersSignInTests(VerifiedOnlyTestCase):
    def test_verifying_on_the_account_page_turns_sign_in_on(self):
        account = APIClient()
        account.force_authenticate(self.staffed)
        sent = account.post(f"/authn/contact-phones/{self.unverified.pk}/request-verification/", {}, format="json")
        self.assertEqual(sent.status_code, 202, sent.data)
        confirmed = account.post(
            f"/authn/contact-phones/{self.unverified.pk}/verify-code/",
            {"code": SMS_CODE, "challenge_id": sent.data["challenge_id"]},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertTrue(confirmed.data["verified"])

        challenge_id = self.request_code(UNVERIFIED).data["challenge_id"]
        response = self.verify(UNVERIFIED, challenge_id, SMS_CODE)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["member_uuid"], str(self.staffed.pk))
        self.assertEqual(self.published_to(), [e164(UNVERIFIED), e164(UNVERIFIED)])

    def test_a_verified_number_signs_in(self):
        challenge_id = self.request_code(VERIFIED).data["challenge_id"]

        response = self.verify(VERIFIED, challenge_id, SMS_CODE)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["member_uuid"], str(self.owner.pk))

    def test_a_number_unverified_after_its_code_was_sent_does_not_sign_in(self):
        challenge_id = self.request_code(VERIFIED).data["challenge_id"]
        ContactPhone.objects.filter(phone_number=VERIFIED).update(verified=False)

        response = self.verify(VERIFIED, challenge_id, SMS_CODE)

        self.assertEqual((response.status_code, response.data), (400, {"detail": VERIFICATION_INVALID}))

    def test_a_number_saved_unverified_after_a_signup_code_was_sent_does_not_sign_in(self):
        challenge_id = self.request_code(UNKNOWN).data["challenge_id"]
        late = Member.objects.create_user(password=None, is_active=True)
        ContactPhone.objects.create(member=late, phone_number=UNKNOWN, region="1-US", verified=False)
        members = Member.objects.count()

        response = self.verify(UNKNOWN, challenge_id, SMS_CODE)

        self.assertEqual((response.status_code, response.data), (400, {"detail": VERIFICATION_INVALID}))
        self.assertEqual(Member.objects.count(), members)
        self.assertFalse(ContactPhone.objects.get(phone_number=UNKNOWN).verified)

    def test_a_member_less_number_is_still_a_signup(self):
        ContactPhone.objects.create(member=None, phone_number=UNKNOWN, region="1-US", verified=False)
        challenge_id = self.request_code(UNKNOWN).data["challenge_id"]

        response = self.verify(UNKNOWN, challenge_id, SMS_CODE)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["message"], "Registration successful.")
        claimed = ContactPhone.objects.get(phone_number=UNKNOWN)
        self.assertEqual((str(claimed.member_id), claimed.verified), (response.data["user"]["member_uuid"], True))

    def test_an_unverified_legacy_copy_of_a_verified_number_does_not_block_its_owner(self):
        # ``phone_number`` is unique, so a number can sit on two members only as a legacy formatted copy (the
        # Normalize Phones tool merges those). Sign-in matches the stored national digits: the verified owner.
        other = Member.objects.create_user(password=None, is_active=True)
        ContactPhone.objects.create(member=other, phone_number="(202) 555-0102", region="1-US", verified=False)
        challenge_id = self.request_code(VERIFIED).data["challenge_id"]

        response = self.verify(VERIFIED, challenge_id, SMS_CODE)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["member_uuid"], str(self.owner.pk))

    def test_an_inactive_account_with_a_verified_number_is_still_refused(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        challenge_id = self.request_code(VERIFIED).data["challenge_id"]

        response = self.verify(VERIFIED, challenge_id, SMS_CODE)

        self.assertEqual((response.status_code, response.data), (400, {"detail": VERIFICATION_INVALID}))
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)

    def test_other_phone_sign_in_paths_ignore_an_unverified_number(self):
        # Password sign-in, password reset and the change-password channel already resolve only verified numbers.
        reset = self.client.post("/authn/password-reset/request-code/", {"identifier": UNVERIFIED}, format="json")
        self.assertEqual(reset.status_code, 202)
        self.publish.assert_not_called()
        self.assertFalse(PhoneVerificationChallenge.objects.exists())

        from apps.authn.services import NoRecoveryChannelError, resolve_login_identifier, select_recovery_channel

        self.assertIsNone(resolve_login_identifier(UNVERIFIED))
        with self.assertRaises(NoRecoveryChannelError):
            select_recovery_channel(self.staffed)
