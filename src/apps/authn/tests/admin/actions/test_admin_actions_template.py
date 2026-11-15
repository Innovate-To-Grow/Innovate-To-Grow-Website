from unittest.mock import patch

from apps.authn.models import (
    ContactEmail,
)
from apps.authn.tests.admin.actions.test_admin_actions import _MemberAdminActionCase, _request


class MemberAdminActionTests(_MemberAdminActionCase):
    def test_download_template_view_success(self):
        request = _request(self.rf, self.admin_user)
        response = self.model_admin.download_template_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("member_import_template.xlsx", response["Content-Disposition"])

    def test_download_template_view_import_error(self):
        request = _request(self.rf, self.admin_user)
        with patch(
            "apps.authn.services.members.import_.generate_template_excel",
            side_effect=ImportError("openpyxl missing"),
        ):
            response = self.model_admin.download_template_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(any("openpyxl missing" in m for m in self._messages(request)))

    def test_import_excel_view_get_renders_form(self):
        request = _request(self.rf, self.admin_user, path="/admin/authn/member/import-excel/")
        response = self.model_admin.import_excel_view(request)
        self.assertEqual(response.status_code, 200)

    def test_import_excel_view_post_stages_a_review(self):
        from apps.authn.models import MemberImportBatch

        response = self.model_admin.import_excel_view(self._upload_request({"mode": "update_existing"}))

        batch = MemberImportBatch.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/admin/authn/member/import-excel/{batch.pk}/review/")
        # Nothing is created before the review is confirmed.
        self.assertFalse(ContactEmail.objects.filter(email_address="imported@example.com").exists())
        self.assertEqual(batch.rows.get().status, "ready_create")

    def test_import_excel_view_update_mode_requires_change_permission(self):
        from apps.authn.models import MemberImportBatch

        request = self._upload_request({"mode": "update_existing"})
        with patch.object(self.model_admin, "has_change_permission", return_value=False):
            response = self.model_admin.import_excel_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You do not have permission to update existing members.")
        self.assertFalse(MemberImportBatch.objects.exists())
