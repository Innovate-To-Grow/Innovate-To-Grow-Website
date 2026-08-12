from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.cli_admin.models import CliAccessToken, CliAuditLog, CliAuthorizationCode
from apps.event.tests.helpers import make_member


class AuthorizationCodeModelTests(TestCase):
    def setUp(self):
        self.member = make_member(email="ac@example.com")

    def _make(self, **kwargs):
        raw = CliAuthorizationCode.generate_raw_code()
        return CliAuthorizationCode.objects.create(
            code_hash=CliAuthorizationCode.hash_code(raw),
            member=self.member,
            code_challenge="x" * 43,
            redirect_uri="http://127.0.0.1:5000/callback",
            **kwargs,
        )

    def test_generate_and_hash_are_deterministic(self):
        raw = CliAuthorizationCode.generate_raw_code()
        self.assertEqual(CliAuthorizationCode.hash_code(raw), CliAuthorizationCode.hash_code(raw))
        self.assertEqual(len(CliAuthorizationCode.hash_code(raw)), 64)

    def test_str(self):
        code = self._make()
        self.assertIn("CLI auth code", str(code))

    def test_is_expired_false_then_true(self):
        fresh = self._make()
        self.assertFalse(fresh.is_expired)
        stale = self._make(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(stale.is_expired)

    def test_try_mark_used_claims_once(self):
        code = self._make()
        competitor = CliAuthorizationCode.objects.get(pk=code.pk)
        self.assertTrue(code.try_mark_used())
        self.assertFalse(competitor.try_mark_used())
        self.assertTrue(code.is_used)
        self.assertIsNotNone(code.used_at)


class AccessTokenModelTests(TestCase):
    def setUp(self):
        self.member = make_member(email="tok@example.com")

    def _make(self, **kwargs):
        raw = CliAccessToken.generate_raw_token()
        return CliAccessToken.objects.create(token_hash=CliAccessToken.hash_token(raw), member=self.member, **kwargs)

    def test_generate_and_hash(self):
        raw = CliAccessToken.generate_raw_token()
        self.assertEqual(len(CliAccessToken.hash_token(raw)), 64)

    def test_str(self):
        self.assertIn("CLI token", str(self._make()))

    def test_validity_states(self):
        valid = self._make()
        self.assertTrue(valid.is_valid)
        self.assertFalse(valid.is_revoked)
        self.assertFalse(valid.is_expired)

        expired = self._make(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(expired.is_expired)
        self.assertFalse(expired.is_valid)

        revoked = self._make(revoked_at=timezone.now())
        self.assertTrue(revoked.is_revoked)
        self.assertFalse(revoked.is_valid)

    def test_touch_last_used_writes_then_throttles(self):
        token = self._make()
        self.assertIsNone(token.last_used_at)
        token.touch_last_used()
        first = token.last_used_at
        self.assertIsNotNone(first)
        # Second call within the throttle window must not write again.
        token.touch_last_used()
        self.assertEqual(token.last_used_at, first)

    def test_touch_last_used_writes_again_after_window(self):
        token = self._make(last_used_at=timezone.now() - timedelta(seconds=600))
        token.touch_last_used()
        self.assertLess((timezone.now() - token.last_used_at).total_seconds(), 5)


class AuditLogModelTests(TestCase):
    def test_str(self):
        log = CliAuditLog.objects.create(
            actor=make_member(email="al@example.com"),
            action="create",
            status="success",
            app_label="projects",
            model_name="semester",
        )
        self.assertIn("Create", str(log))
        self.assertIn("projects.semester", str(log))
