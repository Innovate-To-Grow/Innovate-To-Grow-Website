from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.event.tests.helpers import make_member
from apps.mail.models import LoginLinkToken
from apps.mail.redirects import DEFAULT_LOGIN_REDIRECT_PATH


class LoginLinkTokenModelTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="model@example.com")

    def test_str_active_and_expired(self):
        active = LoginLinkToken(token="t1", member=self.member)
        expired = LoginLinkToken(token="t2", member=self.member, expires_at=timezone.now() - timedelta(seconds=1))

        self.assertIn("active", str(active))
        self.assertIn("expired", str(expired))

    def test_is_valid_true_for_fresh_token(self):
        token = LoginLinkToken.objects.create(token="fresh", member=self.member)
        self.assertTrue(token.is_valid)

    def test_default_expiry_is_seven_days(self):
        before = timezone.now() + timedelta(days=7)
        token = LoginLinkToken.objects.create(token="default-expiry", member=self.member)
        after = timezone.now() + timedelta(days=7)

        self.assertGreaterEqual(token.expires_at, before)
        self.assertLessEqual(token.expires_at, after)

    def test_is_valid_false_when_used(self):
        token = LoginLinkToken.objects.create(token="used", member=self.member)
        token.mark_used()

        token.refresh_from_db()
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.used_at)
        self.assertFalse(token.is_valid)

    def test_try_mark_used_claims_once(self):
        token = LoginLinkToken.objects.create(token="claim", member=self.member)

        first = token.try_mark_used()
        # Reload a separate instance to simulate a competing request.
        competitor = LoginLinkToken.objects.get(pk=token.pk)
        second = competitor.try_mark_used()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.used_at)

    def test_record_reusable_use_does_not_consume(self):
        token = LoginLinkToken.objects.create(token="audit", member=self.member)

        self.assertTrue(token.record_reusable_use())
        token.refresh_from_db()
        self.assertTrue(token.is_used)
        first_used_at = token.used_at

        self.assertTrue(token.record_reusable_use())
        token.refresh_from_db()
        self.assertGreaterEqual(token.used_at, first_used_at)

    def test_record_reusable_use_fails_once_expired_or_revoked(self):
        token = LoginLinkToken.objects.create(
            token="revoked-mid-flight",
            member=self.member,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertFalse(token.record_reusable_use())
        token.refresh_from_db()
        self.assertFalse(token.is_used)

    def test_is_reusable_defaults_false_without_source(self):
        token = LoginLinkToken.objects.create(token="orphan", member=self.member)
        self.assertFalse(token.is_reusable)

    def test_unsafe_token_redirect_path_falls_back_to_default(self):
        token = LoginLinkToken.objects.create(token="unsafe", member=self.member, redirect_path="//evil.example")
        self.assertEqual(token.effective_redirect_path, DEFAULT_LOGIN_REDIRECT_PATH)
