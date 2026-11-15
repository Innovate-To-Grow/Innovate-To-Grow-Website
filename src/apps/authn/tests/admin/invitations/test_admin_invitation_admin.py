from unittest.mock import patch

from apps.authn.admin.security.invitation import AdminInvitationAdmin
from apps.authn.models import (
    AdminInvitation,
    MemberSheetSyncConfig,
    MemberSheetSyncLog,
)
from apps.authn.services.members.sheet_sync.admin import (
    MemberSheetSyncConfigAdmin,
    MemberSheetSyncLogAdmin,
)
from apps.authn.tests.admin.actions.test_admin_actions import _AdminTestBase, _request


class AdminInvitationAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.model_admin = AdminInvitationAdmin(AdminInvitation, self.site)

    def _make_invitation(self, status=None, expires_delta_days=7):
        from django.utils import timezone

        return AdminInvitation.objects.create(
            email="invitee@example.com",
            role=AdminInvitation.Role.ADMIN,
            token=AdminInvitation.generate_token(),
            invited_by=self.admin_user,
            status=status or AdminInvitation.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(days=expires_delta_days),
        )

    def test_get_fieldsets_add(self):
        fieldsets = self.model_admin.get_fieldsets(None, obj=None)
        self.assertEqual(len(fieldsets), 1)

    def test_get_fieldsets_change(self):
        inv = self._make_invitation()
        fieldsets = self.model_admin.get_fieldsets(None, obj=inv)
        self.assertEqual(len(fieldsets), 3)

    def test_get_readonly_fields_change_locks_email(self):
        inv = self._make_invitation()
        fields = self.model_admin.get_readonly_fields(None, obj=inv)
        self.assertIn("email", fields)

    def test_get_readonly_fields_add(self):
        fields = self.model_admin.get_readonly_fields(None, obj=None)
        self.assertNotIn("email", fields)

    def test_status_badge_pending(self):
        inv = self._make_invitation()
        html = self.model_admin.status_badge(inv)
        self.assertIn("span", html)

    def test_status_badge_expired_pending(self):
        inv = self._make_invitation(expires_delta_days=-1)
        html = self.model_admin.status_badge(inv)
        self.assertIn("span", html)

    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_save_model_new_sends_invitation(self, mock_send):
        request = _request(self.rf, self.admin_user, method="post")
        inv = AdminInvitation(email="New@Example.com", role=AdminInvitation.Role.ADMIN)
        with self.captureOnCommitCallbacks(execute=True):
            self.model_admin.save_model(request, inv, form=None, change=False)
        inv.refresh_from_db()
        self.assertEqual(inv.email, "new@example.com")
        self.assertTrue(inv.token)
        mock_send.assert_called_once()
        self.assertTrue(any("created and sent" in m for m in self._messages(request)))

    @patch(
        "apps.authn.services.email.send_admin_invitation_email",
        side_effect=RuntimeError("smtp down"),
    )
    def test_save_model_new_email_failure_warns(self, mock_send):
        request = _request(self.rf, self.admin_user, method="post")
        inv = AdminInvitation(email="fail@example.com", role=AdminInvitation.Role.ADMIN)
        with self.captureOnCommitCallbacks(execute=True):
            self.model_admin.save_model(request, inv, form=None, change=False)
        self.assertTrue(any("could not be sent" in m for m in self._messages(request)))

    def test_save_model_change_does_not_resend(self):
        inv = self._make_invitation()
        request = _request(self.rf, self.admin_user, method="post")
        with patch("apps.authn.services.email.send_admin_invitation_email") as mock_send:
            self.model_admin.save_model(request, inv, form=None, change=True)
        mock_send.assert_not_called()

    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_resend_invitations_sends_and_skips(self, mock_send):
        valid = self._make_invitation()
        expired = self._make_invitation(expires_delta_days=-1)
        request = _request(self.rf, self.admin_user)
        self.model_admin.resend_invitations(request, AdminInvitation.objects.filter(pk__in=[valid.pk, expired.pk]))
        expired.refresh_from_db()
        self.assertEqual(expired.status, AdminInvitation.Status.EXPIRED)
        msgs = self._messages(request)
        self.assertTrue(any("Skipped" in m for m in msgs))
        self.assertTrue(any("Resent" in m for m in msgs))

    @patch("apps.authn.admin.security.invitation.inline_batch_limit", return_value=1)
    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_resend_invitations_refuses_more_than_one_request_can_send(self, mock_send, _limit):
        first, second = self._make_invitation(), self._make_invitation()
        request = _request(self.rf, self.admin_user)

        self.model_admin.resend_invitations(request, AdminInvitation.objects.filter(pk__in=[first.pk, second.pk]))

        mock_send.assert_not_called()
        self.assertTrue(any("cannot be resent from one request" in m for m in self._messages(request)))

    def test_cancel_invitations(self):
        inv = self._make_invitation()
        request = _request(self.rf, self.admin_user)
        self.model_admin.cancel_invitations(request, AdminInvitation.objects.filter(pk=inv.pk))
        inv.refresh_from_db()
        self.assertEqual(inv.status, AdminInvitation.Status.CANCELLED)
        self.assertTrue(any("Cancelled" in m for m in self._messages(request)))


class MemberSheetSyncAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.config_admin = MemberSheetSyncConfigAdmin(MemberSheetSyncConfig, self.site)
        self.log_admin = MemberSheetSyncLogAdmin(MemberSheetSyncLog, self.site)

    def test_sync_error_short_empty(self):
        config = MemberSheetSyncConfig(sync_error="")
        self.assertEqual(self.config_admin.sync_error_short(config), "")

    def test_sync_error_short_truncates(self):
        config = MemberSheetSyncConfig(sync_error="x" * 200)
        html = self.config_admin.sync_error_short(config)
        self.assertIn("span", html)

    def test_log_status_badge_success(self):
        log = MemberSheetSyncLog(status=MemberSheetSyncLog.Status.SUCCESS, sync_type="full", rows_written=3)
        html = self.log_admin.status_badge(log)
        self.assertIn("green", html)

    def test_log_status_badge_failure(self):
        log = MemberSheetSyncLog(status=MemberSheetSyncLog.Status.FAILED, sync_type="full", rows_written=0)
        html = self.log_admin.status_badge(log)
        self.assertIn("red", html)

    def test_error_message_short_empty(self):
        log = MemberSheetSyncLog(error_message="")
        self.assertEqual(self.log_admin.error_message_short(log), "")

    def test_error_message_short_truncates(self):
        log = MemberSheetSyncLog(error_message="e" * 200)
        self.assertEqual(len(self.log_admin.error_message_short(log)), 100)
