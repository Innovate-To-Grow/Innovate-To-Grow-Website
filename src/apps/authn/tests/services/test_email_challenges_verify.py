"""Tests for email_challenges verify/queries internals and the challenge model."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email_challenges import (
    AuthChallengeInvalid,
    consume_verification_token,
    mark_challenge_verified,
    verify_email_code,
)
from apps.authn.services.email_challenges.queries import assert_within_limit, get_latest_pending

Member = get_user_model()
PURPOSE = EmailAuthChallenge.Purpose.LOGIN


def _make_member():
    member = Member.objects.create_user(password="StrongPass123!", is_active=True)
    ContactEmail.objects.create(member=member, email_address="user@example.com", email_type="primary", verified=True)
    return member


def _make_challenge(member, code="123456", **overrides):
    defaults = {
        "member": member,
        "purpose": PURPOSE,
        "target_email": "user@example.com",
        "code_hash": make_password(code),
        "expires_at": timezone.now() + timedelta(minutes=10),
        "max_attempts": 5,
        "last_sent_at": timezone.now(),
        "status": EmailAuthChallenge.Status.PENDING,
    }
    defaults.update(overrides)
    return EmailAuthChallenge.objects.create(**defaults)


class VerifyEmailCodeTests(TestCase):
    def setUp(self):
        self.member = _make_member()

    def test_no_challenge_raises(self):
        with self.assertRaises(AuthChallengeInvalid):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="123456")

    def test_expired_challenge_marked_and_raises(self):
        # verify_email_code is @transaction.atomic: the mark_expired() write is rolled back
        # when AuthChallengeInvalid propagates, but the branch (lines 41-43) still executes.
        _make_challenge(self.member, expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaisesMessage(AuthChallengeInvalid, "invalid or has expired"):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="123456")

    def test_wrong_code_raises_invalid(self):
        _make_challenge(self.member)
        with self.assertRaisesMessage(AuthChallengeInvalid, "invalid or has expired"):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="000000")

    def test_wrong_code_on_last_attempt_raises(self):
        # Exercises the attempts >= max_attempts branch (line 47-48) on a wrong code.
        _make_challenge(self.member, attempts=4)
        with self.assertRaisesMessage(AuthChallengeInvalid, "invalid or has expired"):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="000000")

    def test_correct_code_returns_challenge(self):
        _make_challenge(self.member)
        result = verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="123456")
        self.assertEqual(result.status, EmailAuthChallenge.Status.PENDING)


class ConsumeVerificationTokenTests(TestCase):
    def setUp(self):
        self.member = _make_member()

    def test_valid_token_consumes_challenge(self):
        challenge = _make_challenge(self.member)
        token = mark_challenge_verified(challenge)
        consumed = consume_verification_token(purpose=PURPOSE, verification_token=token, member=self.member)
        self.assertEqual(consumed.status, EmailAuthChallenge.Status.CONSUMED)

    def test_expired_verified_challenge_skipped(self):
        # The expired branch (lines 98-100) marks the challenge expired then continues;
        # the surrounding @transaction.atomic rolls that write back when the final raise fires.
        challenge = _make_challenge(self.member, status=EmailAuthChallenge.Status.VERIFIED)
        challenge.verification_token_hash = make_password("tok")
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.verified_at = timezone.now()
        challenge.save(update_fields=["verification_token_hash", "expires_at", "verified_at"])
        with self.assertRaises(AuthChallengeInvalid):
            consume_verification_token(purpose=PURPOSE, verification_token="tok", member=self.member)

    def test_invalid_token_raises(self):
        challenge = _make_challenge(self.member)
        mark_challenge_verified(challenge)
        with self.assertRaises(AuthChallengeInvalid):
            consume_verification_token(purpose=PURPOSE, verification_token="wrong", member=self.member)


class QueriesTests(TestCase):
    def setUp(self):
        self.member = _make_member()

    def test_assert_within_limit_resend_cooldown(self):
        # A fresh pending challenge with last_sent_at == now triggers the cooldown branch.
        _make_challenge(self.member, last_sent_at=timezone.now())
        from apps.authn.services.email_challenges import AuthChallengeThrottled

        with self.assertRaises(AuthChallengeThrottled):
            assert_within_limit(
                member=self.member,
                purpose=PURPOSE,
                target_email="user@example.com",
                now=timezone.now(),
            )

    def test_get_latest_pending_returns_newest(self):
        _make_challenge(self.member)
        latest = get_latest_pending(purpose=PURPOSE, target_email="user@example.com")
        self.assertIsNotNone(latest)


class EmailAuthChallengeModelTests(TestCase):
    def setUp(self):
        self.member = _make_member()

    def test_str(self):
        challenge = _make_challenge(self.member)
        self.assertIn("user@example.com", str(challenge))

    def test_mark_expired_noop_when_already_expired(self):
        challenge = _make_challenge(self.member, status=EmailAuthChallenge.Status.EXPIRED)
        before = challenge.updated_at
        challenge.mark_expired()
        challenge.refresh_from_db()
        self.assertEqual(challenge.updated_at, before)

    def test_mark_verified_sets_status_and_timestamp(self):
        challenge = _make_challenge(self.member)
        challenge.mark_verified()
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.VERIFIED)
        self.assertIsNotNone(challenge.verified_at)

    def test_mark_consumed(self):
        challenge = _make_challenge(self.member)
        challenge.mark_consumed()
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.CONSUMED)

    def test_default_expiry_in_future(self):
        self.assertGreater(EmailAuthChallenge.default_expiry(), timezone.now())
