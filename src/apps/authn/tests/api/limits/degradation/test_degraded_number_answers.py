from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import ContactPhone, PhoneVerificationChallenge
from apps.authn.services.email.challenges.degradation import DEGRADED_MAX_ATTEMPTS, FAILURE_THRESHOLD
from apps.authn.services.sms import sns_verify
from apps.authn.tests.api.limits.degradation.test_code_guess_degradation_api import (
    DEGRADED_PHONE,
    FRESH_PHONE,
    Member,
    e164,
)
from apps.authn.tests.helpers.sms_provider import SMS_CODE, WRONG_CODE, patch_sms_provider
from apps.event.tests.helpers import make_event


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DegradedNumberAnswersTests(TestCase):
    """Every endpoint that checks an SMS code, with the real service below it (only the provider is replaced).

    One number has ten failed guesses behind it, the other none. Each test sends both a code through one flow and
    compares the answers to a wrong guess.
    """

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.publish = patch_sms_provider(self)
        PhoneVerificationChallenge.objects.create(
            phone_number=e164(DEGRADED_PHONE),
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password(SMS_CODE),
            status=PhoneVerificationChallenge.Status.EXPIRED,
            attempts=FAILURE_THRESHOLD,
            max_attempts=sns_verify.MAX_VERIFY_ATTEMPTS,
            expires_at=timezone.now(),
            send_reserved_at=timezone.now(),
        )

    @staticmethod
    def latest_challenge(national):
        return PhoneVerificationChallenge.objects.filter(phone_number=e164(national)).latest("send_reserved_at")

    @staticmethod
    def phone_member(national, *, verified=True):
        member = Member.objects.create_user(password=None, is_active=True)
        phone = ContactPhone.objects.create(member=member, phone_number=national, region="1-US", verified=verified)
        return member, phone

    def assert_degradation_is_invisible(self, request_code, guess, *, sent=202):
        """``request_code(national)`` asks for a code; ``guess(national, challenge_id, code)`` checks one."""
        requests = {national: request_code(national) for national in (DEGRADED_PHONE, FRESH_PHONE)}
        for response in requests.values():
            self.assertEqual(response.status_code, sent, response.data)
        self.assertEqual(sorted(requests[DEGRADED_PHONE].data), sorted(requests[FRESH_PHONE].data))
        self.assertEqual(self.latest_challenge(DEGRADED_PHONE).max_attempts, DEGRADED_MAX_ATTEMPTS)
        self.assertEqual(self.latest_challenge(FRESH_PHONE).max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)

        wrong = {
            national: guess(national, requests[national].data["challenge_id"], WRONG_CODE)
            for national in (DEGRADED_PHONE, FRESH_PHONE)
        }

        # The first wrong guess on the fresh number is the plain invalid answer; the degraded number gets the same.
        self.assertEqual(wrong[FRESH_PHONE].status_code, 400)
        self.assertEqual(wrong[DEGRADED_PHONE].status_code, wrong[FRESH_PHONE].status_code)
        self.assertEqual(wrong[DEGRADED_PHONE].data, wrong[FRESH_PHONE].data)

        # The code is spent all the same: one guess used it up, and the right code gets that same invalid answer.
        spent, live = self.latest_challenge(DEGRADED_PHONE), self.latest_challenge(FRESH_PHONE)
        self.assertEqual((spent.attempts, spent.status), (1, PhoneVerificationChallenge.Status.EXPIRED))
        self.assertEqual((live.attempts, live.status), (1, PhoneVerificationChallenge.Status.PENDING))
        late = guess(DEGRADED_PHONE, requests[DEGRADED_PHONE].data["challenge_id"], SMS_CODE)
        self.assertEqual((late.status_code, late.data), (wrong[FRESH_PHONE].status_code, wrong[FRESH_PHONE].data))

        # Not a lock: the next code sent to the degraded number verifies on a correct first try.
        again = request_code(DEGRADED_PHONE)
        self.assertEqual(again.status_code, sent, again.data)
        self.assertEqual(self.latest_challenge(DEGRADED_PHONE).max_attempts, DEGRADED_MAX_ATTEMPTS)
        approved = guess(DEGRADED_PHONE, again.data["challenge_id"], SMS_CODE)
        self.assertEqual(approved.status_code, 200, approved.data)

    def test_passwordless_phone_auth(self):
        self.assert_degradation_is_invisible(
            lambda national: self.client.post(
                "/authn/phone-auth/request-code/", {"phone_number": national}, format="json"
            ),
            lambda national, challenge_id, code: self.client.post(
                "/authn/phone-auth/verify-code/",
                {"phone_number": national, "challenge_id": challenge_id, "code": code},
                format="json",
            ),
        )

    def test_password_reset_by_phone(self):
        for national in (DEGRADED_PHONE, FRESH_PHONE):
            self.phone_member(national)

        self.assert_degradation_is_invisible(
            lambda national: self.client.post(
                "/authn/password-reset/request-code/", {"identifier": national}, format="json"
            ),
            lambda national, challenge_id, code: self.client.post(
                "/authn/password-reset/verify-code/",
                {"identifier": national, "challenge_id": challenge_id, "code": code},
                format="json",
            ),
        )

    def test_password_change_by_sms(self):
        # Phone-only members: with no verified email the change-password code goes out by SMS.
        members = {national: self.phone_member(national)[0] for national in (DEGRADED_PHONE, FRESH_PHONE)}

        def request_code(national):
            self.client.force_authenticate(members[national])
            return self.client.post("/authn/change-password/request-code/", {}, format="json")

        def guess(national, challenge_id, code):
            self.client.force_authenticate(members[national])
            return self.client.post(
                "/authn/change-password/verify-code/", {"challenge_id": challenge_id, "code": code}, format="json"
            )

        self.assert_degradation_is_invisible(request_code, guess)

    def test_contact_phone_verification(self):
        owners = {national: self.phone_member(national, verified=False) for national in (DEGRADED_PHONE, FRESH_PHONE)}

        def request_code(national):
            member, phone = owners[national]
            self.client.force_authenticate(member)
            return self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/", {}, format="json")

        def guess(national, challenge_id, code):
            member, phone = owners[national]
            self.client.force_authenticate(member)
            return self.client.post(
                f"/authn/contact-phones/{phone.pk}/verify-code/",
                {"challenge_id": challenge_id, "code": code},
                format="json",
            )

        self.assert_degradation_is_invisible(request_code, guess)

    def test_event_registration_phone_code(self):
        event = make_event(registration_open=True, collect_phone=True, verify_phone=True)
        self.client.force_authenticate(Member.objects.create_user(password=None, is_active=True))

        self.assert_degradation_is_invisible(
            lambda national: self.client.post(
                "/event/send-phone-code/", {"phone": national, "event_slug": event.slug}, format="json"
            ),
            lambda national, challenge_id, code: self.client.post(
                "/event/verify-phone-code/",
                {"phone": national, "challenge_id": challenge_id, "code": code, "event_slug": event.slug},
                format="json",
            ),
            sent=200,
        )

    def test_a_normal_code_still_answers_throttled_on_its_last_guess(self):
        """Only the degraded answer changed: five wrong guesses on a normal code end with the verifier's 429."""
        request = self.client.post("/authn/phone-auth/request-code/", {"phone_number": FRESH_PHONE}, format="json")

        statuses = [
            self.client.post(
                "/authn/phone-auth/verify-code/",
                {"phone_number": FRESH_PHONE, "challenge_id": request.data["challenge_id"], "code": WRONG_CODE},
                format="json",
            ).status_code
            for _ in range(sns_verify.MAX_VERIFY_ATTEMPTS + 1)
        ]

        self.assertEqual(statuses, [400, 400, 400, 400, 429, 400])
