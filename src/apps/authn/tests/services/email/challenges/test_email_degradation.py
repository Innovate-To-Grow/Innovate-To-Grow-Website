from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password

from apps.authn.models import ContactEmail
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
    FAILURE_WINDOW,
    recent_email_failures,
)
from apps.authn.services.email.challenges.issue import create_challenge_record
from apps.authn.tests.services.email.challenges.test_code_guess_degradation import (
    BASELINE_GUESSES_PER_HOUR,
    CODE,
    LOGIN,
    WRONG,
    DegradationTestCase,
    Member,
)


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
