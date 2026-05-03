from django.test import override_settings
from django.urls import reverse

from .base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminPageTests(SystemIntelligenceAdminBase):
    @override_settings(ROOT_URLCONF="core.urls")
    def test_main_page_embeds_adk_web_shell(self):
        response = self.client.get(reverse("admin:core_system_intelligence"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="System Intelligence ADK Web"')
        self.assertContains(response, 'src="/admin/core/system-intelligence/adk/dev-ui/"')
        self.assertNotContains(response, "Legacy approval chat")
        self.assertNotContains(response, 'id="si-root"')

    def test_legacy_page_is_removed(self):
        response = self.client.get("/admin/core/system-intelligence/legacy/")

        self.assertEqual(response.status_code, 404)
