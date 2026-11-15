"""Direct unit tests for authn admin actions and helper methods.

These call admin action methods directly via a RequestFactory request wired
with message storage, sidestepping the confirm-on-save flow.
"""

import uuid
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings

from apps.authn.admin.members.member import MemberAdmin
from apps.authn.models import (
    ContactEmail,
)

Member = get_user_model()


def _request(rf, user, method="get", path="/admin/", data=None):
    req = getattr(rf, method)(path, data or {})
    req.user = user
    req.session = {}
    req._messages = FallbackStorage(req)
    return req


class _AdminTestBase(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.site = AdminSite()
        self.admin_user = Member.objects.create_superuser(
            password="admin123", first_name="Admin", last_name="User", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.admin_user, email_address="admin@example.com", email_type="primary", verified=True
        )

    def _messages(self, request):
        return [str(m) for m in request._messages]


class _MemberAdminActionCase(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.model_admin = MemberAdmin(Member, self.site)
        self.m1 = Member.objects.create_user(password="t", first_name="Mem", last_name="One", is_active=False)
        ContactEmail.objects.create(member=self.m1, email_address="m1@example.com", email_type="primary")

    def _upload_request(self, data):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import Workbook

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["Primary Email", "First Name", "Last Name", "Organization"])
        worksheet.append(["imported@example.com", "Imp", "Orted", "Acme"])
        payload = BytesIO()
        workbook.save(payload)
        upload = SimpleUploadedFile(
            "members.xlsx",
            payload.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        request = self.rf.post("/admin/authn/member/import-excel/", {"excel_file": upload, **data})
        request.user = self.admin_user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request


class MemberAdminActionTests(_MemberAdminActionCase):
    def test_get_primary_email_display(self):
        self.assertEqual(self.model_admin.get_primary_email_display(self.m1), "m1@example.com")

    def test_get_primary_email_display_dash_when_missing(self):
        bare = Member.objects.create_user(password="t", first_name="No", last_name="Email")
        self.assertEqual(self.model_admin.get_primary_email_display(bare), "-")

    def test_get_full_name_display(self):
        self.assertEqual(self.model_admin.get_full_name_display(self.m1), "Mem One")

    def test_activate_members_action(self):
        request = _request(self.rf, self.admin_user)
        self.model_admin.activate_members(request, Member.objects.filter(pk=self.m1.pk))
        self.m1.refresh_from_db()
        self.assertTrue(self.m1.is_active)
        self.assertIn("1 member(s) activated.", self._messages(request))

    def test_deactivate_members_action(self):
        self.m1.is_active = True
        self.m1.save(update_fields=["is_active"])
        request = _request(self.rf, self.admin_user)
        self.model_admin.deactivate_members(request, Member.objects.filter(pk=self.m1.pk))
        self.m1.refresh_from_db()
        self.assertFalse(self.m1.is_active)
        self.assertIn("1 member(s) deactivated.", self._messages(request))

    def test_export_members_to_excel_action(self):
        request = _request(self.rf, self.admin_user)
        response = self.model_admin.export_members_to_excel(request, Member.objects.all())
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml.sheet", response["Content-Type"])
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_export_members_to_vcard_action(self):
        request = _request(self.rf, self.admin_user)
        response = self.model_admin.export_members_to_vcard(request, Member.objects.all())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/vcard"))

    @patch("apps.authn.services.members.sheet_sync.sync_members_to_sheet", return_value=7)
    def test_sync_all_members_to_sheet_success(self, mock_sync):
        request = _request(self.rf, self.admin_user)
        self.model_admin.sync_all_members_to_sheet(request, Member.objects.all())
        self.assertIn("Synced 7 members to Google Sheet.", self._messages(request))

    @patch(
        "apps.authn.services.members.sheet_sync.sync_members_to_sheet",
        side_effect=RuntimeError("sheets down"),
    )
    def test_sync_all_members_to_sheet_failure(self, mock_sync):
        request = _request(self.rf, self.admin_user)
        self.model_admin.sync_all_members_to_sheet(request, Member.objects.all())
        self.assertTrue(any("Sheet sync failed" in m for m in self._messages(request)))

    def test_ensure_new_member_uuid_assigns_when_blank(self):
        obj = Member(first_name="X", last_name="Y")
        obj.id = "None"
        MemberAdmin._ensure_new_member_uuid(obj, change=False)
        self.assertIsInstance(obj.id, uuid.UUID)

    def test_ensure_new_member_uuid_skips_on_change(self):
        existing = self.m1.id
        MemberAdmin._ensure_new_member_uuid(self.m1, change=True)
        self.assertEqual(self.m1.id, existing)

    @override_settings(FRONTEND_URL="https://frontend.example.com")
    def test_impersonate_view_redirects_with_token(self):
        request = _request(
            self.rf, self.admin_user, method="post", path=f"/admin/authn/member/{self.m1.pk}/impersonate/"
        )
        response = self.model_admin.impersonate_view(request, str(self.m1.pk))
        self.assertEqual(response.status_code, 302)
        self.assertIn("https://frontend.example.com/impersonate-login#token=", response.url)

    def test_impersonate_view_rejects_get(self):
        """Minting a token on GET skips CSRF entirely, so a cross-site navigation could force it."""
        request = _request(self.rf, self.admin_user, path=f"/admin/authn/member/{self.m1.pk}/impersonate/")
        with self.assertRaises(PermissionDenied):
            self.model_admin.impersonate_view(request, str(self.m1.pk))

    def test_impersonate_view_404s_on_a_malformed_id(self):
        """A non-UUID <path:object_id> used to raise ValidationError out of the view as a 500."""
        from django.http import Http404

        request = _request(self.rf, self.admin_user, method="post", path="/admin/authn/member/nope/impersonate/")
        with self.assertRaises(Http404):
            self.model_admin.impersonate_view(request, "nope")
