"""Dark-mode contrast regression tests for authn admin status badges.

Dark mode in the Unfold admin is driven by a ``.dark`` class on ``<html>``;
the surface becomes near-black (``#131314``). Status badges therefore must use
colors legible on BOTH the light (``#fffbfb``) and dark (``#131314``) surfaces.

Two badges live in this app:

* ``AdminInvitationAdmin.status_badge`` paints white text on a *saturated*
  background pill. White-on-saturated reads on either surface, so it is
  mode-safe and intentionally left unchanged. These tests lock that rendering.
* ``MemberSheetSyncLogAdmin.status_badge`` sets a *text-only* color that sits
  directly on the admin surface. The CSS named color ``green`` (``#008000``) is
  too dark to read on the dark surface, so it was replaced with the saturated
  ``#10b981`` / ``#ef4444`` palette. These tests lock that fix.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.admin.member_sheet_sync import MemberSheetSyncLogAdmin
from apps.authn.admin.members.invitation import AdminInvitationAdmin
from apps.authn.models import AdminInvitation, MemberSheetSyncLog
from apps.event.tests.helpers import make_superuser

# CSS named colors that render too dark to read on the near-black dark-mode
# admin surface (#131314). A text-only badge must never use these.
DARK_TEXT_COLORS = ("#008000", "#000000", "#000080", "#333", "#333333", "#222")


class AdminInvitationBadgeDarkModeTests(TestCase):
    """The invitation pill is white-on-saturated-background: mode-safe."""

    # color:#fff on a saturated background reads on both light and dark.
    EXPECTED = {
        AdminInvitation.Status.PENDING: "#f59e0b",
        AdminInvitation.Status.ACCEPTED: "#10b981",
        AdminInvitation.Status.CANCELLED: "#ef4444",
    }

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def _make_invitation(self, status, **kwargs):
        defaults = {
            "email": f"{status}@example.com",
            "token": AdminInvitation.generate_token(),
            "status": status,
            "expires_at": timezone.now() + timezone.timedelta(days=7),
            "invited_by": self.admin_user,
        }
        defaults.update(kwargs)
        return AdminInvitation.objects.create(**defaults)

    def test_status_badge_uses_white_text_on_saturated_background(self):
        admin_obj = AdminInvitationAdmin(AdminInvitation, None)
        for status, expected_color in self.EXPECTED.items():
            inv = self._make_invitation(status)
            html = admin_obj.status_badge(inv)
            with self.subTest(status=status):
                self.assertIn("color:#fff", html)
                self.assertIn(f"background:{expected_color};", html)
                # The pill is a filled background, so no dark-on-dark text risk.
                for dark in DARK_TEXT_COLORS:
                    self.assertNotIn(f"color:{dark}", html.replace(" ", ""))

    def test_expired_pending_renders_gray_pill(self):
        inv = self._make_invitation(
            AdminInvitation.Status.PENDING,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        html = AdminInvitationAdmin(AdminInvitation, None).status_badge(inv)
        self.assertIn("color:#fff", html)
        self.assertIn("background:#6b7280;", html)

    def test_changelist_renders_badge_html(self):
        self._make_invitation(AdminInvitation.Status.PENDING)
        response = self.client.get(reverse("admin:authn_admininvitation_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "color:#fff")
        self.assertContains(response, "background:#f59e0b;")


class MemberSheetSyncLogBadgeDarkModeTests(TestCase):
    """The sync-log badge is text-only, so the color must be dark-mode legible."""

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def _make_log(self, status):
        return MemberSheetSyncLog.objects.create(
            sync_type=MemberSheetSyncLog.SyncType.FULL,
            status=status,
            rows_written=1,
        )

    def test_success_badge_uses_dark_mode_legible_green(self):
        log = MemberSheetSyncLog(status=MemberSheetSyncLog.Status.SUCCESS, sync_type="full")
        html = MemberSheetSyncLogAdmin(MemberSheetSyncLog, None).status_badge(log)
        self.assertIn("#10b981", html)
        # Must never regress to the dark CSS "green" (#008000) or a literal name.
        compact = html.replace(" ", "")
        self.assertNotIn("color:green", compact)
        for dark in DARK_TEXT_COLORS:
            self.assertNotIn(f"color:{dark}", compact)

    def test_failure_badge_uses_legible_red(self):
        log = MemberSheetSyncLog(status=MemberSheetSyncLog.Status.FAILED, sync_type="full")
        html = MemberSheetSyncLogAdmin(MemberSheetSyncLog, None).status_badge(log)
        self.assertIn("#ef4444", html)
        self.assertNotIn("color:red", html.replace(" ", ""))

    def test_changelist_renders_legible_status_colors(self):
        self._make_log(MemberSheetSyncLog.Status.SUCCESS)
        self._make_log(MemberSheetSyncLog.Status.FAILED)
        response = self.client.get(reverse("admin:authn_membersheetsynclog_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#10b981")
        self.assertContains(response, "#ef4444")
        # The dark CSS "green" must not appear anywhere in the rendered list.
        self.assertNotContains(response, "#008000")
