from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import (
    AuthChallengeInvalid,
    verify_email_code,
    verify_email_code_and_mint_token,
)
from apps.authn.services.email.challenges.queries import assert_within_limit, get_latest_pending
from apps.authn.tests.services.email.challenges.test_email_challenges_verify import (
    PURPOSE,
    _make_challenge,
    _make_member,
)


class QueriesTests(TestCase):
    def setUp(self):
        self.member = _make_member()

    def test_assert_within_limit_resend_cooldown(self):
        # A fresh pending challenge with last_sent_at == now triggers the cooldown branch.
        _make_challenge(self.member, last_sent_at=timezone.now())
        from apps.authn.services.email.challenges import AuthChallengeThrottled

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


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row-lock semantics")
class EmailChallengeConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.member = _make_member()

    @staticmethod
    def _run_concurrently(action):
        barrier = Barrier(2)

        def attempt():
            close_old_connections()
            barrier.wait()
            try:
                return action()
            except AuthChallengeInvalid:
                return None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: attempt(), range(2)))

    def test_only_one_caller_can_consume_a_correct_code(self):
        challenge = _make_challenge(self.member)

        def verify():
            return verify_email_code(
                purpose=PURPOSE,
                target_email="user@example.com",
                code="123456",
            ).pk

        results = self._run_concurrently(verify)
        self.assertEqual(sum(result is not None for result in results), 1)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.CONSUMED)

    def test_only_one_caller_can_mint_a_verification_token(self):
        challenge = _make_challenge(self.member)

        def verify_and_mint():
            _, token = verify_email_code_and_mint_token(
                purpose=PURPOSE,
                target_email="user@example.com",
                code="123456",
                member=self.member,
            )
            return token

        results = self._run_concurrently(verify_and_mint)
        self.assertEqual(sum(result is not None for result in results), 1)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, EmailAuthChallenge.Status.VERIFIED)
