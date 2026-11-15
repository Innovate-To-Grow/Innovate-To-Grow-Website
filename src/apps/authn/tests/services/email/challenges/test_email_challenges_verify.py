"""Tests for email.challenges verify/queries internals and the challenge model."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import (
    AuthChallengeInvalid,
    consume_verification_token,
    mark_challenge_verified,
    verify_email_code,
    verify_email_code_and_mint_token,
)

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
        challenge = _make_challenge(self.member, expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaisesMessage(AuthChallengeInvalid, "invalid or has expired"):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="123456")
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.EXPIRED)

    def test_wrong_code_raises_invalid(self):
        challenge = _make_challenge(self.member)
        with self.assertRaisesMessage(AuthChallengeInvalid, "invalid or has expired"):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="000000")
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 1)

    def test_wrong_code_on_last_attempt_raises(self):
        challenge = _make_challenge(self.member, attempts=4)
        with self.assertRaisesMessage(AuthChallengeInvalid, "invalid or has expired"):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="000000")
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 5)
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.EXPIRED)

    def test_correct_code_consumes_challenge(self):
        _make_challenge(self.member)
        result = verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="123456")
        self.assertEqual(result.status, EmailAuthChallenge.Status.CONSUMED)
        with self.assertRaises(AuthChallengeInvalid):
            verify_email_code(purpose=PURPOSE, target_email="user@example.com", code="123456")

    def test_correct_code_returns_approved_callback_result(self):
        challenge = _make_challenge(self.member)

        result = verify_email_code(
            purpose=PURPOSE,
            target_email="user@example.com",
            code="123456",
            approved_callback=lambda approved: f"approved:{approved.pk}",
        )

        self.assertEqual(result, f"approved:{challenge.pk}")
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.CONSUMED)

    def test_approved_callback_failure_rolls_back_code_and_member_write(self):
        challenge = _make_challenge(self.member)
        original_first_name = self.member.first_name

        def fail_after_member_write(_approved):
            Member.objects.filter(pk=self.member.pk).update(first_name="Not committed")
            raise RuntimeError("JWT creation failed")

        with self.assertRaisesMessage(RuntimeError, "JWT creation failed"):
            verify_email_code(
                purpose=PURPOSE,
                target_email="user@example.com",
                code="123456",
                approved_callback=fail_after_member_write,
            )

        challenge.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.PENDING)
        self.assertEqual(self.member.first_name, original_first_name)

    def test_correct_code_and_token_creation_are_one_transition(self):
        challenge = _make_challenge(self.member)
        verified, token = verify_email_code_and_mint_token(
            purpose=PURPOSE,
            target_email="user@example.com",
            code="123456",
            member=self.member,
        )
        self.assertEqual(verified.status, EmailAuthChallenge.Status.VERIFIED)
        self.assertTrue(token)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.VERIFIED)
        with self.assertRaises(AuthChallengeInvalid):
            verify_email_code_and_mint_token(
                purpose=PURPOSE,
                target_email="user@example.com",
                code="123456",
                member=self.member,
            )


class ConsumeVerificationTokenTests(TestCase):
    def setUp(self):
        self.member = _make_member()

    def test_valid_token_consumes_challenge(self):
        challenge = _make_challenge(self.member)
        token = mark_challenge_verified(challenge)
        consumed = consume_verification_token(purpose=PURPOSE, verification_token=token, member=self.member)
        self.assertEqual(consumed.status, EmailAuthChallenge.Status.CONSUMED)
        with self.assertRaises(AuthChallengeInvalid):
            consume_verification_token(purpose=PURPOSE, verification_token=token, member=self.member)

    def test_expired_verified_challenge_skipped(self):
        challenge = _make_challenge(self.member, status=EmailAuthChallenge.Status.VERIFIED)
        challenge.verification_token_hash = make_password("tok")
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.verified_at = timezone.now()
        challenge.save(update_fields=["verification_token_hash", "expires_at", "verified_at"])
        with self.assertRaises(AuthChallengeInvalid):
            consume_verification_token(purpose=PURPOSE, verification_token="tok", member=self.member)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.EXPIRED)

    def test_invalid_token_raises(self):
        challenge = _make_challenge(self.member)
        mark_challenge_verified(challenge)
        with self.assertRaises(AuthChallengeInvalid):
            consume_verification_token(purpose=PURPOSE, verification_token="wrong", member=self.member)

    def test_challenge_can_only_transition_to_verified_once(self):
        challenge = _make_challenge(self.member)
        mark_challenge_verified(challenge)
        with self.assertRaises(AuthChallengeInvalid):
            mark_challenge_verified(challenge)
