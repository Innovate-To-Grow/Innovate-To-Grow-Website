from datetime import timedelta

from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.cli_admin.models import CliAccessToken, CliAuditLog, CliAuthorizationCode
from apps.cli_admin.tests.helpers import make_member, make_superuser


class AdminTests(TestCase):
    def setUp(self):
        self.superuser = make_superuser(email="admin@example.com")
        self.member = make_member(email="subject@example.com")
        self.client.force_login(self.superuser)
        self.factory = RequestFactory()
        self.token_admin = django_admin.site._registry[CliAccessToken]
        self.code_admin = django_admin.site._registry[CliAuthorizationCode]
        self.log_admin = django_admin.site._registry[CliAuditLog]

    def _token(self, **kwargs):
        raw = CliAccessToken.generate_raw_token()
        return CliAccessToken.objects.create(token_hash=CliAccessToken.hash_token(raw), member=self.member, **kwargs)

    # ---- display methods ------------------------------------------------
    def test_token_validity_states(self):
        valid = self._token()
        revoked = self._token(revoked_at=timezone.now())
        expired = self._token(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.token_admin.validity(valid), ("valid", "success"))
        self.assertEqual(self.token_admin.validity(revoked), ("revoked", "danger"))
        self.assertEqual(self.token_admin.validity(expired), ("expired", "warning"))

    def test_authcode_is_expired_display(self):
        raw = CliAuthorizationCode.generate_raw_code()
        fresh = CliAuthorizationCode.objects.create(
            code_hash=CliAuthorizationCode.hash_code(raw),
            member=self.member,
            code_challenge="x" * 43,
            redirect_uri="http://127.0.0.1:5000/callback",
        )
        stale = CliAuthorizationCode.objects.create(
            code_hash=CliAuthorizationCode.hash_code(raw + "2"),
            member=self.member,
            code_challenge="x" * 43,
            redirect_uri="http://127.0.0.1:5000/callback",
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertFalse(self.code_admin.is_expired_display(fresh))
        self.assertTrue(self.code_admin.is_expired_display(stale))

    def test_auditlog_badges_and_error_short(self):
        ok = CliAuditLog.objects.create(
            actor=self.member, action="create", status="success", app_label="projects", model_name="semester"
        )
        bad = CliAuditLog.objects.create(
            actor=self.member,
            action="delete",
            status="failed",
            app_label="projects",
            model_name="semester",
            error_message="boom " * 40,
        )
        self.assertEqual(self.log_admin.action_badge(ok)[0], "Create")
        self.assertEqual(self.log_admin.status_badge(ok), ("Success", "success"))
        self.assertEqual(self.log_admin.status_badge(bad), ("Failed", "danger"))
        self.assertEqual(self.log_admin.error_short(ok), "—")
        self.assertEqual(len(self.log_admin.error_short(bad)), 80)

    # ---- revoke action --------------------------------------------------
    def test_revoke_selected_action(self):
        valid = self._token()
        request = self.factory.post("/admin/cli_admin/cliaccesstoken/")
        request.user = self.superuser
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        self.token_admin.revoke_selected(request, CliAccessToken.objects.filter(pk=valid.pk))
        valid.refresh_from_db()
        self.assertIsNotNone(valid.revoked_at)

    def test_revoke_action_survives_get_actions(self):
        request = self.factory.get("/admin/cli_admin/cliaccesstoken/")
        request.user = self.superuser
        self.assertIn("revoke_selected", self.token_admin.get_actions(request))

    # ---- read-only + no secrets -----------------------------------------
    def test_admins_are_read_only(self):
        request = self.factory.get("/")
        request.user = self.superuser
        for model_admin in (self.token_admin, self.code_admin, self.log_admin):
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_delete_permission(request))

    def test_changelists_render_without_hashes(self):
        token = self._token()
        code_raw = CliAuthorizationCode.generate_raw_code()
        code = CliAuthorizationCode.objects.create(
            code_hash=CliAuthorizationCode.hash_code(code_raw),
            member=self.member,
            code_challenge="x" * 43,
            redirect_uri="http://127.0.0.1:5000/callback",
        )
        CliAuditLog.objects.create(
            actor=self.member, action="create", status="success", app_label="projects", model_name="semester"
        )
        for url, secret in (
            ("/admin/cli_admin/cliaccesstoken/", token.token_hash),
            ("/admin/cli_admin/cliauthorizationcode/", code.code_hash),
            ("/admin/cli_admin/cliauditlog/", ""),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            if secret:
                self.assertNotContains(response, secret)
