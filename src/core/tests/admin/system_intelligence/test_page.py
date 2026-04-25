from unittest.mock import patch

from django.urls import reverse

from .base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminPageTests(SystemIntelligenceAdminBase):
    def test_chat_page_renders_context_usage_in_input_bar(self):
        with patch(
            "core.services.bedrock.get_available_models",
            return_value=[("Anthropic", [(self.aws_config.default_model_id, "Claude")])],
        ):
            response = self.client.get(reverse("admin:core_system_intelligence"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="si-context-usage"')
        self.assertContains(response, 'id="si-context-usage-detail"')
        self.assertContains(response, "0% full · 0 / 200k")
        self.assertNotContains(response, 'id="si-context-tooltip"')
        self.assertContains(response, 'data-context-window="200000"')
