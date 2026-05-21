from django.urls import reverse

from event.tests.helpers import make_superuser
from system_intelligence.models import SystemIntelligenceExport
from system_intelligence.services import actions
from system_intelligence.services.exports import create_export
from system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class ExportDownloadViewTests(SystemIntelligenceAdminBase):
    def setUp(self):
        super().setUp()
        self.context_tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            self.export = create_export(app_label="authn", model_name="Member")
        finally:
            actions.reset_action_context(self.context_tokens)

    def test_owner_downloads_xlsx_attachment(self):
        url = reverse("admin:system_intelligence_export_download", args=[self.export.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(self.export.filename, response["Content-Disposition"])

    def test_other_admin_cannot_download_someone_elses_export(self):
        other = make_superuser(email="other@example.com")
        self.client.force_login(other)
        url = reverse("admin:system_intelligence_export_download", args=[self.export.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_missing_file_returns_410(self):
        SystemIntelligenceExport.objects.filter(pk=self.export.pk).update(file="")
        url = reverse("admin:system_intelligence_export_download", args=[self.export.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 410)
