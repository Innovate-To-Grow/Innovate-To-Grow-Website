"""Scope and one-use guarantees for event registration email proofs."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import EmailAuthChallenge
from apps.authn.services.email.challenges import (
    AuthChallengeInvalid,
    consume_verification_token,
    issue_email_challenge,
    verify_email_code_and_mint_token,
)
from apps.event.tests.helpers import make_member


class EventEmailChallengeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member()
        self.email = "secondary@example.com"
        self.context = f"event-registration:{uuid.uuid4()}"
        self.challenge = EmailAuthChallenge.objects.create(
            member=self.member,
            purpose=EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
            target_email=self.email,
            context_identifier=self.context,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def _verify(self, **overrides):
        return verify_email_code_and_mint_token(
            **{
                "purpose": EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
                "target_email": self.email,
                "code": "123456",
                "member": self.member,
                "challenge_id": self.challenge.pk,
                "context_identifier": self.context,
                **overrides,
            }
        )

    def _consume(self, token, **overrides):
        return consume_verification_token(
            **{
                "purpose": EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
                "verification_token": token,
                "member": self.member,
                "target_email": self.email,
                "challenge_id": self.challenge.pk,
                "context_identifier": self.context,
                **overrides,
            }
        )

    def test_verify_rejects_each_wrong_scope_without_consuming_code(self):
        other_member = make_member(email="other@example.com")
        for mismatch in (
            {"purpose": EmailAuthChallenge.Purpose.CONTACT_EMAIL_VERIFY},
            {"member": other_member},
            {"target_email": "different@example.com"},
            {"challenge_id": uuid.uuid4()},
            {"context_identifier": f"event-registration:{uuid.uuid4()}"},
        ):
            with self.subTest(mismatch=mismatch), self.assertRaises(AuthChallengeInvalid):
                self._verify(**mismatch)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, EmailAuthChallenge.Status.PENDING)
        self.assertEqual(self.challenge.attempts, 0)
        self._verify()

    def test_token_matches_exact_scope_and_is_single_use(self):
        _, token = self._verify()
        other_member = make_member(email="other@example.com")
        for mismatch in (
            {"purpose": EmailAuthChallenge.Purpose.PASSWORD_CHANGE},
            {"member": other_member},
            {"target_email": "different@example.com"},
            {"challenge_id": uuid.uuid4()},
            {"context_identifier": f"event-registration:{uuid.uuid4()}"},
            {"verification_token": "wrong-token"},
        ):
            with self.subTest(mismatch=mismatch), self.assertRaises(AuthChallengeInvalid):
                self._consume(token, **mismatch)
        consumed = self._consume(token, target_email=self.email.upper())
        self.assertEqual(consumed.status, EmailAuthChallenge.Status.CONSUMED)
        with self.assertRaises(AuthChallengeInvalid):
            self._consume(token)
        with self.assertRaises(AuthChallengeInvalid):
            self._verify()

    def test_consumption_rolls_back_with_registration_transaction(self):
        _, token = self._verify()
        with self.assertRaisesMessage(RuntimeError, "registration failed"):
            with transaction.atomic():
                self._consume(token)
                raise RuntimeError("registration failed")
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, EmailAuthChallenge.Status.VERIFIED)
        self._consume(token)

    def test_expired_code_and_expired_token_are_rejected(self):
        EmailAuthChallenge.objects.filter(pk=self.challenge.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(AuthChallengeInvalid):
            self._verify()
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, EmailAuthChallenge.Status.EXPIRED)
        EmailAuthChallenge.objects.filter(pk=self.challenge.pk).update(
            status=EmailAuthChallenge.Status.PENDING,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        _, token = self._verify()
        EmailAuthChallenge.objects.filter(pk=self.challenge.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(AuthChallengeInvalid):
            self._consume(token)

    def test_wrong_attempts_persist_and_exhaust_challenge(self):
        for _ in range(self.challenge.max_attempts):
            with self.assertRaises(AuthChallengeInvalid):
                self._verify(code="000000")
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.attempts, self.challenge.max_attempts)
        self.assertEqual(self.challenge.status, EmailAuthChallenge.Status.EXPIRED)
        with self.assertRaises(AuthChallengeInvalid):
            self._verify()

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_resend_expires_only_same_event_challenge(self, send):
        other = EmailAuthChallenge.objects.create(
            member=self.member,
            purpose=self.challenge.purpose,
            target_email=self.email,
            context_identifier=f"event-registration:{uuid.uuid4()}",
            code_hash=make_password("654321"),
            expires_at=self.challenge.expires_at,
        )
        issued = issue_email_challenge(
            member=self.member,
            purpose=self.challenge.purpose,
            target_email=self.email.upper(),
            context_identifier=self.context,
        )
        self.challenge.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.challenge.status, EmailAuthChallenge.Status.EXPIRED)
        self.assertEqual(other.status, EmailAuthChallenge.Status.PENDING)
        self.assertEqual(issued.context_identifier, self.context)
        self.assertEqual(issued.target_email, self.email)
        send.assert_called_once()

    def test_exact_challenge_does_not_select_other_member_latest_email(self):
        EmailAuthChallenge.objects.create(
            member=make_member(email="other@example.com"),
            purpose=self.challenge.purpose,
            target_email=self.email,
            context_identifier=self.context,
            code_hash=make_password("654321"),
            expires_at=self.challenge.expires_at,
        )
        challenge, _ = self._verify()
        self.assertEqual(challenge.pk, self.challenge.pk)
