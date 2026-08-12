from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.cli_admin.models import CliAccessToken, CliAuthorizationCode
from apps.event.tests.helpers import make_member


class CleanupCommandTests(TestCase):
    def setUp(self):
        self.member = make_member(email="cleanup@example.com")

    def _token(self, **kwargs):
        raw = CliAccessToken.generate_raw_token()
        return CliAccessToken.objects.create(token_hash=CliAccessToken.hash_token(raw), member=self.member, **kwargs)

    def _code(self, **kwargs):
        raw = CliAuthorizationCode.generate_raw_code()
        return CliAuthorizationCode.objects.create(
            code_hash=CliAuthorizationCode.hash_code(raw),
            member=self.member,
            code_challenge="x" * 43,
            redirect_uri="http://127.0.0.1:5000/callback",
            **kwargs,
        )

    def test_cleanup_removes_expired_and_revoked(self):
        past = timezone.now() - timedelta(hours=1)
        future = timezone.now() + timedelta(hours=1)

        expired_code = self._code(expires_at=past)
        live_code = self._code(expires_at=future)
        expired_token = self._token(expires_at=past)
        revoked_token = self._token(expires_at=future, revoked_at=past)
        live_token = self._token(expires_at=future)

        out = StringIO()
        call_command("cli_admin_cleanup", stdout=out)

        self.assertFalse(CliAuthorizationCode.objects.filter(pk=expired_code.pk).exists())
        self.assertTrue(CliAuthorizationCode.objects.filter(pk=live_code.pk).exists())
        self.assertFalse(CliAccessToken.objects.filter(pk=expired_token.pk).exists())
        self.assertFalse(CliAccessToken.objects.filter(pk=revoked_token.pk).exists())
        self.assertTrue(CliAccessToken.objects.filter(pk=live_token.pk).exists())
        self.assertIn("Removed", out.getvalue())
