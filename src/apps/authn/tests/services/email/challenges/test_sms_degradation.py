from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.hashers import make_password

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.email.challenges.degradation import (
    DEGRADED_MAX_ATTEMPTS,
    FAILURE_WINDOW,
)
from apps.authn.services.sms import challenges, sns_verify
from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    check_phone_verification,
    start_phone_verification,
)
from apps.authn.tests.services.email.challenges.test_code_guess_degradation import (
    CODE,
    PHONE_AUTH,
    WRONG,
    DegradationTestCase,
)


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

        self.assertEqual(challenges._recent_phone_failures(self.PHONE, now=self.clock.now), 9)
        self.assertEqual(self.issue().max_attempts, sns_verify.MAX_VERIFY_ATTEMPTS)

    def test_the_failure_count_is_one_query(self):
        self.record_failures(5, 5)
        self.record_failures(4, phone="+12025550199")

        with self.assertNumQueries(1):
            self.assertEqual(challenges._recent_phone_failures(self.PHONE, now=self.clock.now), 10)

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
