from django.test import override_settings
from django.urls import NoReverseMatch, reverse

from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminPageTests(SystemIntelligenceAdminBase):
    @override_settings(ROOT_URLCONF="config.urls")
    def test_main_page_renders_custom_chat_shell(self):
        response = self.client.get(reverse("admin:system_intelligence"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="si-root"')
        self.assertContains(response, "Conversations")
        self.assertContains(response, "System Intelligence")
        self.assertContains(response, "Model")
        self.assertContains(response, self.chat_config.default_model_id)
        self.assertContains(response, "Message AI Assistant")
        self.assertNotContains(response, "Welcome")
        self.assertNotContains(response, "Agent Debug")
        self.assertContains(response, "data-si-sidebar-toggle")
        self.assertContains(response, 'aria-controls="si-chat-sidebar-body"')
        self.assertContains(response, 'id="si-chat-sidebar-body"')
        self.assertContains(response, "system_intelligence/css/chat-layout.css")
        self.assertContains(response, "system_intelligence/css/chat-sidebar.css")
        self.assertContains(response, "system_intelligence/js/chat-state.js")
        self.assertNotContains(response, "system-intelligence/debug")

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
        self.assertContains(
            response, "/admin/system-intelligence/exports/00000000-0000-0000-0000-000000000000/download/"
        )
        self.assertContains(response, "Plan Mode")
        self.assertContains(response, 'data-si-command="retry"')
        self.assertContains(response, 'data-si-command="compact"')

    def test_debug_page_route_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:system_intelligence_debug")

        response = self.client.get("/admin/system-intelligence/debug/")
        self.assertEqual(response.status_code, 404)

    def test_agent_debug_backend_route_is_removed(self):
        removed_backend_path = "/admin/system-intelligence/" + "".join(("a", "d", "k")) + "/dev-ui/"
        response = self.client.get(removed_backend_path)

        self.assertEqual(response.status_code, 404)

    def test_legacy_page_is_removed(self):
        response = self.client.get("/admin/system-intelligence/legacy/")

        self.assertEqual(response.status_code, 404)

    def test_old_core_path_is_removed(self):
        response = self.client.get("/admin/core/system-intelligence/")

        self.assertEqual(response.status_code, 404)
