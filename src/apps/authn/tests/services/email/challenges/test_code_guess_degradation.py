"""Per-destination code-guess degradation (``apps.authn.services.email.challenges.degradation``).

A destination (normalised email / E.164 phone) with >= 10 failed code guesses in the last 24 hours gets single-guess
codes; never keyed on the client IP, never a lock. Challenge rows here are real, and so are the guesses where a test
is about behaviour; direct row fixtures only stand in for "N failures already happened".
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import (
    MAX_CHALLENGES_PER_HOUR,
    MAX_VERIFY_ATTEMPTS,
)
from apps.authn.services.email.challenges.degradation import (
    DEGRADED_MAX_ATTEMPTS,
    FAILURE_THRESHOLD,
    FAILURE_WINDOW,
    max_attempts_for,
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
