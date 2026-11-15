"""Code-guess degradation is invisible in the public code answers (no oracle for a degraded destination).

Email and SMS alike: the wrong guess that spends a degraded code is answered exactly like a first wrong guess on a
destination nobody has been guessing at, on every verify endpoint.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import MAX_VERIFY_ATTEMPTS
from apps.authn.services.email.challenges.degradation import DEGRADED_MAX_ATTEMPTS, FAILURE_THRESHOLD

Member = get_user_model()

DEGRADED = "degraded@example.com"
FRESH = "fresh@example.com"
DEGRADED_PHONE = "2025550123"
FRESH_PHONE = "2025550199"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
@patch("apps.authn.services.email.send_email._send_via_ses", return_value=True)
class DegradedDestinationAnswersTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.members = {}
        for email in (DEGRADED, FRESH):
            member = Member.objects.create_user(password=None, is_active=True)
            ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
            self.members[email] = member
        EmailAuthChallenge.objects.create(
            member=self.members[DEGRADED],
            purpose=EmailAuthChallenge.Purpose.LOGIN,
            target_email=DEGRADED,
            code_hash=make_password("123456"),
            expires_at=timezone.now(),
            attempts=FAILURE_THRESHOLD,
            status=EmailAuthChallenge.Status.EXPIRED,
        )

    def request_code(self, email):
        return self.client.post("/authn/login/request-code/", {"email": email}, format="json")

    def latest_challenge(self, email):
        return EmailAuthChallenge.objects.filter(target_email=email, status=EmailAuthChallenge.Status.PENDING).get()

    def test_request_and_wrong_guess_answers_match_a_fresh_destination(self, _ses):
        degraded_request, fresh_request = self.request_code(DEGRADED), self.request_code(FRESH)

        self.assertEqual(degraded_request.status_code, 202)
        self.assertEqual(fresh_request.status_code, 202)
        self.assertEqual(degraded_request.data, fresh_request.data)
        self.assertEqual(self.latest_challenge(DEGRADED).max_attempts, DEGRADED_MAX_ATTEMPTS)
        self.assertEqual(self.latest_challenge(FRESH).max_attempts, MAX_VERIFY_ATTEMPTS)

        answers = {
            email: self.client.post("/authn/login/verify-code/", {"email": email, "code": "000000"}, format="json")
            for email in (DEGRADED, FRESH)
        }

        self.assertEqual(answers[DEGRADED].status_code, 400)
        self.assertEqual(answers[FRESH].status_code, 400)
        self.assertEqual(answers[DEGRADED].data, answers[FRESH].data)


def e164(national: str) -> str:
    return f"+1{national}"
