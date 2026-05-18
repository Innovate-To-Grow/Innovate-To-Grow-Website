from django.test import override_settings
from django.urls import reverse

from system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminPageTests(SystemIntelligenceAdminBase):
    @override_settings(ROOT_URLCONF="core.urls")
    def test_main_page_renders_custom_chat_shell(self):
        response = self.client.get(reverse("admin:system_intelligence"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="si-root"')
        self.assertContains(response, "Message System Intelligence")
        self.assertContains(response, "ADK Debug")
        self.assertContains(response, reverse("admin:system_intelligence_debug"))
        self.assertContains(response, "system_intelligence/css/chat-layout.css")
        self.assertContains(response, "system_intelligence/js/chat-state.js")
        self.assertNotContains(response, 'title="System Intelligence ADK Web"')
        self.assertNotContains(response, 'src="/admin/system-intelligence/adk/dev-ui/"')

    def test_main_page_renders_chat_endpoint_config_and_controls(self):
        response = self.client.get(reverse("admin:system_intelligence"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "si-chat-config")
        self.assertContains(response, reverse("admin:system_intelligence_conversations"))
        self.assertContains(response, reverse("admin:system_intelligence_new"))
        self.assertContains(response, "00000000-0000-0000-0000-000000000000")
        self.assertContains(
            response, "/admin/system-intelligence/actions/00000000-0000-0000-0000-000000000000/approve/"
        )
        self.assertContains(response, "/admin/system-intelligence/actions/00000000-0000-0000-0000-000000000000/reject/")
        self.assertContains(
            response, "/admin/system-intelligence/actions/00000000-0000-0000-0000-000000000000/preview/"
        )
        self.assertContains(response, "Plan Mode")
        self.assertContains(response, 'data-si-command="retry"')
        self.assertContains(response, 'data-si-command="compact"')

    def test_debug_page_embeds_adk_web_shell(self):
        response = self.client.get(reverse("admin:system_intelligence_debug"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="System Intelligence ADK Web"')
        self.assertContains(response, 'src="/admin/system-intelligence/adk/dev-ui/"')
        self.assertNotContains(response, 'id="si-root"')

    def test_legacy_page_is_removed(self):
        response = self.client.get("/admin/system-intelligence/legacy/")

        self.assertEqual(response.status_code, 404)

    def test_old_core_path_is_removed(self):
        response = self.client.get("/admin/core/system-intelligence/")

        self.assertEqual(response.status_code, 404)
