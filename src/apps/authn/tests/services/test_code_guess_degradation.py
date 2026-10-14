"""Per-destination code-guess degradation (``apps.authn.services.email.challenges.degradation``).

A destination (normalised email / E.164 phone) with >= 10 failed code guesses in the last 24 hours gets single-guess
codes; never keyed on the client IP, never a lock. Challenge rows here are real, and so are the guesses where a test
is about behaviour; direct row fixtures only stand in for "N failures already happened".
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail, PhoneVerificationChallenge
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import (
    MAX_CHALLENGES_PER_HOUR,
    MAX_VERIFY_ATTEMPTS,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    verify_email_code,
)
from apps.authn.services.email.challenges.degradation import (
    DEGRADED_MAX_ATTEMPTS,
    FAILURE_THRESHOLD,
    FAILURE_WINDOW,
    max_attempts_for,
    recent_email_failures,
)
from apps.authn.services.email.challenges.issue import create_challenge_record
from apps.authn.services.sms import sns_verify
from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    check_phone_verification,
    start_phone_verification,
)

Member = get_user_model()

CODE = "123456"
WRONG = "000000"
LOGIN = EmailAuthChallenge.Purpose.LOGIN
PHONE_AUTH = PhoneVerificationChallenge.Purpose.PHONE_AUTH
BASELINE_GUESSES_PER_HOUR = MAX_CHALLENGES_PER_HOUR * MAX_VERIFY_ATTEMPTS  # 10 codes x 5 guesses = 50


class Clock:
    """Stand-in for ``django.utils.timezone.now`` (row timestamps, windows and expiry all read it)."""

    def __init__(self):
        self.now = timezone.now()

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


# Codes are hashed like passwords; a fast hasher keeps the simulated attacker hours quick.
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DegradationTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.clock = Clock()
        for target, value in (
            ("django.utils.timezone.now", self.clock),
            ("apps.authn.services.email.challenges._random_code", lambda: CODE),
            ("apps.authn.services.sms.sns_verify._random_code", lambda: CODE),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class MaxAttemptsPolicyTests(TestCase):
    def test_threshold_boundary(self):
        self.assertEqual(max_attempts_for(FAILURE_THRESHOLD - 1, default=5), 5)
        self.assertEqual(max_attempts_for(FAILURE_THRESHOLD, default=5), DEGRADED_MAX_ATTEMPTS)
        self.assertEqual(max_attempts_for(FAILURE_THRESHOLD + 40, default=5), DEGRADED_MAX_ATTEMPTS)

    def test_policy_values(self):
        self.assertEqual((FAILURE_THRESHOLD, FAILURE_WINDOW, DEGRADED_MAX_ATTEMPTS), (10, timedelta(hours=24), 1))


class EmailDegradationTests(DegradationTestCase):
    EMAIL = "student@example.com"

    def setUp(self):
        super().setUp()
        self.member = self.make_member(self.EMAIL)

    @staticmethod
    def make_member(email):
        member = Member.objects.create_user(password=None, is_active=True)
        ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
        return member

    def record_failures(self, *attempts, email=EMAIL, purpose=LOGIN, age=timedelta(0)):
        """Rows standing for challenges that already took ``attempts`` wrong guesses (each), issued ``age`` ago."""
        for count in attempts:
            row = EmailAuthChallenge.objects.create(
                member=self.member,
                purpose=purpose,
                target_email=email,
                code_hash=make_password(CODE),
                expires_at=self.clock.now + timedelta(minutes=10),
                attempts=count,
                status=EmailAuthChallenge.Status.EXPIRED,
            )
            EmailAuthChallenge.objects.filter(pk=row.pk).update(created_at=self.clock.now - age)

    def issue(self, email=EMAIL, purpose=LOGIN, member=None):
        challenge, _code = create_challenge_record(member=member or self.member, purpose=purpose, target_email=email)
        return challenge

    def guess(self, code, email=EMAIL, purpose=LOGIN):
        """True when the code verified; False on the (single, uniform) invalid answer."""
        try:
            verify_email_code(purpose=purpose, target_email=email, code=code)
        except AuthChallengeInvalid:
            return False
        return True

    def test_nine_failures_keep_the_default_ten_degrade(self):
        self.record_failures(5, 4)
        self.assertEqual(self.issue().max_attempts, MAX_VERIFY_ATTEMPTS)

        self.record_failures(1)
        self.clock.advance(minutes=2)  # past the resend cooldown
        self.assertEqual(self.issue().max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_failures_count_across_purposes_and_apply_to_every_purpose(self):
        self.record_failures(5, purpose=LOGIN)
        self.record_failures(5, purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET)

        for purpose in (LOGIN, EmailAuthChallenge.Purpose.REGISTER, EmailAuthChallenge.Purpose.CONTACT_EMAIL_VERIFY):
            with self.subTest(purpose=purpose):
                self.assertEqual(self.issue(purpose=purpose).max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_a_correct_first_try_still_verifies_under_degradation(self):
        self.record_failures(5, 5)
        self.issue()

        self.assertTrue(self.guess(CODE))

    def test_a_degraded_code_takes_one_guess_and_answers_like_any_invalid_code(self):
        self.record_failures(5, 5)
        challenge = self.issue()

        with self.assertRaisesMessage(AuthChallengeInvalid, "Verification code is invalid or has expired."):
            verify_email_code(purpose=LOGIN, target_email=self.EMAIL, code=WRONG)
        # The code is spent: even the right code no longer verifies, with the same answer.
        self.assertFalse(self.guess(CODE))
        challenge.refresh_from_db()
        self.assertEqual((challenge.attempts, challenge.status), (1, EmailAuthChallenge.Status.EXPIRED))

    def test_existing_challenges_keep_their_limit(self):
        pending = self.issue()
        self.record_failures(5, 5, purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET)

        self.issue(purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET)

        pending.refresh_from_db()
        self.assertEqual(pending.max_attempts, MAX_VERIFY_ATTEMPTS)
        self.assertEqual(sum(self.guess(WRONG) for _ in range(MAX_VERIFY_ATTEMPTS - 1)), 0)
        self.assertTrue(self.guess(CODE))

    def test_failures_roll_off_after_24_hours(self):
        self.record_failures(5, 5, age=FAILURE_WINDOW - timedelta(minutes=1))
        self.assertEqual(self.issue().max_attempts, DEGRADED_MAX_ATTEMPTS)

        self.clock.advance(minutes=2)

        self.assertEqual(self.issue().max_attempts, MAX_VERIFY_ATTEMPTS)

    def test_destinations_are_independent(self):
        other = "someone-else@example.com"
        self.make_member(other)
        self.record_failures(5, 5)

        self.assertEqual(self.issue(email=other).max_attempts, MAX_VERIFY_ATTEMPTS)
        self.assertEqual(self.issue().max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_the_destination_is_the_normalised_address(self):
        self.record_failures(5, 5)

        self.assertEqual(self.issue(email="  Student@Example.COM ").max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_successful_verifications_are_not_counted(self):
        # Two codes that each took four wrong guesses and then the right one, and a third with one wrong guess:
        # nine failures. Counting the three successful checks as well would make twelve and degrade.
        for wrong_guesses in (4, 4, 1):
            self.issue()
            self.assertEqual(sum(self.guess(WRONG) for _ in range(wrong_guesses)), 0)
            self.assertTrue(self.guess(CODE))
            self.clock.advance(minutes=2)

        self.assertEqual(recent_email_failures(self.EMAIL, now=self.clock.now), 9)
        self.assertEqual(self.issue().max_attempts, MAX_VERIFY_ATTEMPTS)

    def test_the_failure_count_is_one_query(self):
        self.record_failures(5, 3, purpose=LOGIN)
        self.record_failures(2, purpose=EmailAuthChallenge.Purpose.ADMIN_LOGIN)

        with self.assertNumQueries(1):
            self.assertEqual(recent_email_failures(self.EMAIL, now=self.clock.now), 10)

    def attacker_hour(self):
        """Request every code the hourly cap allows and guess each one until it is dead; return guesses evaluated."""
        issued = []
        for _ in range(MAX_CHALLENGES_PER_HOUR):
            issued.append(self.issue().pk)
            for _ in range(MAX_VERIFY_ATTEMPTS):
                self.assertFalse(self.guess(WRONG))
            self.clock.advance(minutes=5)
        with self.assertRaises(AuthChallengeThrottled):
            self.issue()
        self.clock.advance(minutes=11)  # the next hour: the first code above has left the hourly cap's window
        return sum(EmailAuthChallenge.objects.filter(pk__in=issued).values_list("attempts", flat=True))

    def test_an_attacker_hour_is_bounded_by_the_hourly_send_cap(self):
        first_hour = self.attacker_hour()
        later_hours = [self.attacker_hour() for _ in range(3)]

        # Two full codes reach the threshold, then every code is single-guess.
        self.assertEqual(first_hour, 2 * MAX_VERIFY_ATTEMPTS + (MAX_CHALLENGES_PER_HOUR - 2) * DEGRADED_MAX_ATTEMPTS)
        self.assertEqual(later_hours, [MAX_CHALLENGES_PER_HOUR] * 3)
        self.assertLess(first_hour, BASELINE_GUESSES_PER_HOUR)

    def test_without_degradation_an_attacker_hour_gets_fifty_guesses(self):
        with patch("apps.authn.services.email.challenges.degradation.FAILURE_THRESHOLD", 10**6):
            self.assertEqual([self.attacker_hour() for _ in range(2)], [BASELINE_GUESSES_PER_HOUR] * 2)


class SmsDegradationTests(DegradationTestCase):
    PHONE = "+12025550123"

    def setUp(self):
        super().setUp()
        aws_config = MagicMock()
        aws_config.render_sms_otp_message.side_effect = lambda code: f"Your code is {code}"
        for target, kwargs in (
            ("apps.authn.services.sms.sns_verify._assert_configured", {"return_value": aws_config}),
            ("apps.authn.services.sms.sns_verify._publish_sms", {"return_value": "msg-1"}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def record_failures(self, *attempts, phone=PHONE, age=timedelta(0)):
        """Spent challenges that already took ``attempts`` wrong guesses (each), issued ``age`` ago."""
        for count in attempts:
            PhoneVerificationChallenge.objects.create(
                phone_number=phone,
                purpose=PHONE_AUTH,
                code_hash=make_password(CODE),
                status=PhoneVerificationChallenge.Status.EXPIRED,
                attempts=count,
                max_attempts=5,
                expires_at=self.clock.now - age + timedelta(minutes=10),
                send_reserved_at=self.clock.now - age,
            )

    def issue(self, phone=PHONE, purpose=PHONE_AUTH):
        started = start_phone_verification(phone, purpose=purpose)
        return PhoneVerificationChallenge.objects.get(pk=started["challenge_id"])

    @staticmethod
    def guess(challenge, code, purpose=PHONE_AUTH):
        """``"approved"``, or the answer of the SMS verifier: ``"invalid"`` / ``"throttled"``."""
        try:
            check_phone_verification(challenge.phone_number, code, challenge_id=challenge.pk, purpose=purpose)
        except PhoneVerificationThrottled:
            return "throttled"
        except PhoneVerificationInvalid:
            return "invalid"
        return "approved"

    def test_nine_failures_keep_the_default_ten_degrade(self):
        self.record_failures(5, 4)
        self.assertEqual(self.issue().max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)

        self.record_failures(1)
        self.assertEqual(self.issue().max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_degradation_applies_to_every_purpose(self):
        self.record_failures(5, 5)

        for purpose in (
            PhoneVerificationChallenge.Purpose.PASSWORD_RESET,
            PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
        ):
            with self.subTest(purpose=purpose):
                self.assertEqual(self.issue(purpose=purpose).max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_a_correct_first_try_still_verifies_under_degradation(self):
        self.record_failures(5, 5)
        challenge = self.issue()

        self.assertEqual(self.guess(challenge, CODE), "approved")

    def test_a_degraded_code_takes_one_guess_and_answers_like_any_invalid_code(self):
        """The one guess spends the code, and is answered like a first wrong guess on any other number."""
        self.record_failures(5, 5)
        challenge = self.issue()

        self.assertEqual(self.guess(challenge, WRONG), "invalid")
        self.assertEqual(self.guess(challenge, CODE), "invalid")  # spent: even the right code no longer verifies
        challenge.refresh_from_db()
        self.assertEqual((challenge.attempts, challenge.status), (1, PhoneVerificationChallenge.Status.EXPIRED))

    def test_a_normal_code_keeps_the_throttled_answer_on_its_last_guess(self):
        challenge = self.issue()

        answers = [self.guess(challenge, WRONG) for _ in range(sns_verify.MAX_VERIFY_ATTEMPTS + 1)]

        self.assertEqual(answers, ["invalid"] * (sns_verify.MAX_VERIFY_ATTEMPTS - 1) + ["throttled", "invalid"])

    def test_a_degraded_code_found_out_of_attempts_also_answers_invalid(self):
        """The defensive branch: a still-verifiable row that already used its attempts (it is expired on sight)."""
        self.record_failures(5, 5)
        degraded, normal = self.issue(), self.issue(phone="+12025550199")
        for challenge in (degraded, normal):
            PhoneVerificationChallenge.objects.filter(pk=challenge.pk).update(attempts=challenge.max_attempts)

        self.assertEqual(self.guess(degraded, CODE), "invalid")
        self.assertEqual(self.guess(normal, CODE), "throttled")
        degraded.refresh_from_db()
        self.assertEqual(degraded.status, PhoneVerificationChallenge.Status.EXPIRED)

    def test_existing_challenges_keep_their_limit(self):
        pending = self.issue(purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION)
        self.record_failures(5, 5)

        self.issue()

        pending.refresh_from_db()
        self.assertEqual(pending.max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)

    def test_failures_roll_off_after_24_hours(self):
        self.record_failures(5, 5, age=FAILURE_WINDOW - timedelta(minutes=1))
        self.assertEqual(self.issue().max_attempts, DEGRADED_MAX_ATTEMPTS)

        self.clock.advance(minutes=2)

        self.assertEqual(self.issue().max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)

    def test_destinations_are_independent(self):
        self.record_failures(5, 5)

        self.assertEqual(self.issue(phone="+12025550199").max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)
        self.assertEqual(self.issue().max_attempts, DEGRADED_MAX_ATTEMPTS)

    def test_successful_verifications_are_not_counted(self):
        for wrong_guesses in (4, 4, 1):
            challenge = self.issue()
            self.assertEqual({self.guess(challenge, WRONG) for _ in range(wrong_guesses)}, {"invalid"})
            self.assertEqual(self.guess(challenge, CODE), "approved")
            self.clock.advance(minutes=2)

        self.assertEqual(sns_verify._recent_phone_failures(self.PHONE, now=self.clock.now), 9)
        self.assertEqual(self.issue().max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)

    def test_the_failure_count_is_one_query(self):
        self.record_failures(5, 5)
        self.record_failures(4, phone="+12025550199")

        with self.assertNumQueries(1):
            self.assertEqual(sns_verify._recent_phone_failures(self.PHONE, now=self.clock.now), 10)

    def attacker_hour(self):
        issued = []
        for _ in range(MAX_SENDS_PER_HOUR):
            challenge = self.issue()
            issued.append(challenge.pk)
            for _ in range(sns_verify.MAX_VERIFY_ATTEMPTS):
                self.assertNotEqual(self.guess(challenge, WRONG), "approved")
            self.clock.advance(minutes=5)
        with self.assertRaises(PhoneVerificationThrottled):
            self.issue()
        self.clock.advance(minutes=11)
        return sum(PhoneVerificationChallenge.objects.filter(pk__in=issued).values_list("attempts", flat=True))

    def test_an_attacker_hour_is_bounded_by_the_hourly_send_cap(self):
        first_hour = self.attacker_hour()
        later_hours = [self.attacker_hour() for _ in range(3)]

        self.assertEqual(first_hour, 2 * sns_verify.MAX_VERIFY_ATTEMPTS + (MAX_SENDS_PER_HOUR - 2))
        self.assertEqual(later_hours, [MAX_SENDS_PER_HOUR] * 3)

    def test_without_degradation_an_attacker_hour_gets_fifty_guesses(self):
        with patch("apps.authn.services.email.challenges.degradation.FAILURE_THRESHOLD", 10**6):
            self.assertEqual(
                [self.attacker_hour() for _ in range(2)], [MAX_SENDS_PER_HOUR * sns_verify.MAX_VERIFY_ATTEMPTS] * 2
            )
