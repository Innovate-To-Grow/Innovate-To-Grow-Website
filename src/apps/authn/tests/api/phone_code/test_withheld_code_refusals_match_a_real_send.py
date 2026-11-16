from unittest.mock import patch

from rest_framework.test import APIClient

from apps.authn.constants import VERIFICATION_INVALID, VERIFICATION_THROTTLED
from apps.authn.models import ContactPhone, PhoneVerificationChallenge, SendQuotaWindow
from apps.authn.services.send_verification.guard import quotas
from apps.authn.services.sms import PhoneVerificationBusy, PhoneVerificationDeliveryError
from apps.authn.services.sms.sns_verify import MAX_SENDS_PER_HOUR
from apps.authn.tests.api.phone_code.test_phone_code_verified_only import (
    BUDGET,
    BUDGET_DAY,
    UNKNOWN,
    UNVERIFIED,
    VERIFIED,
    Member,
    VerifiedOnlyTestCase,
    e164,
)
from apps.authn.tests.helpers.sms_provider import SMS_CODE


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
