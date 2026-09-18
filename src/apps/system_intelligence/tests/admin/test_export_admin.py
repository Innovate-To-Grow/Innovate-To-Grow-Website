from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser
from apps.system_intelligence.admin.export_admin import SystemIntelligenceExportAdmin
from apps.system_intelligence.models import SystemIntelligenceExport
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.exports import create_export
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceExportAdminTests(SystemIntelligenceAdminBase):
    def setUp(self):
        super().setUp()
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            self.export = create_export(app_label="authn", model_name="Member")
        finally:
            actions.reset_action_context(tokens)
        self.model_admin = admin.site._registry[SystemIntelligenceExport]
        self.download_url = reverse("admin:system_intelligence_export_download", args=[self.export.pk])

    def test_registered_read_only_apart_from_delete(self):
        self.assertIsInstance(self.model_admin, SystemIntelligenceExportAdmin)
        request = RequestFactory().get("/")
        request.user = self.admin_user
        self.assertFalse(self.model_admin.has_add_permission(request))
        self.assertTrue(self.model_admin.has_delete_permission(request, self.export))
        self.assertIn("filename", self.model_admin.readonly_fields)
        self.assertIn("download_link", self.model_admin.readonly_fields)

    def test_changelist_and_detail_render(self):
        response = self.client.get(reverse("admin:system_intelligence_systemintelligenceexport_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.export.filename)
        self.assertContains(response, self.download_url)

        response = self.client.get(
            reverse("admin:system_intelligence_systemintelligenceexport_change", args=[self.export.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.download_url)
        self.assertContains(response, ", ".join(self.export.field_names))

    def test_file_column_only_links_when_the_viewer_can_download(self):
        other_super = make_superuser(email="other-super@example.com")
        request = RequestFactory().get("/")

        request.user = self.admin_user
        column = self.model_admin.get_list_display(request)[-1]
        self.assertIn(self.download_url, str(column(self.export)))

        request.user = other_super
        column = self.model_admin.get_list_display(request)[-1]
        self.assertIn(self.download_url, str(column(self.export)))

        request.user = make_admin(apps=["system_intelligence"], email="plain-staff@example.com")
        column = self.model_admin.get_list_display(request)[-1]
        self.assertEqual(column(self.export), self.export.filename)

    def test_download_link_reports_missing_file(self):
        SystemIntelligenceExport.objects.filter(pk=self.export.pk).update(file="")
        self.export.refresh_from_db()
        self.assertEqual(str(self.model_admin.download_link(self.export)), "File is missing on storage.")

    def test_field_names_display_handles_empty(self):
        self.assertEqual(self.model_admin.field_names_display(SystemIntelligenceExport(field_names=[])), "—")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_admin_delete_removes_file_from_storage(self):
        storage, name = self.export.file.storage, self.export.file.name
        self.assertTrue(storage.exists(name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("admin:system_intelligence_systemintelligenceexport_delete", args=[self.export.pk]),
                {"post": "yes"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SystemIntelligenceExport.objects.filter(pk=self.export.pk).exists())
        self.assertFalse(storage.exists(name))
