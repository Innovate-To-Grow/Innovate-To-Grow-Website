"""``/compact`` is gated on the default route: a usable API-key provider needs no AWS, a disabled one is refused."""

import json
from unittest.mock import patch

from django.urls import reverse

from apps.system_intelligence.models import ChatMessage
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase
from apps.system_intelligence.tests.services.agents.provider_runtime.helpers import ProviderStoreMixin, make_provider

SUMMARY_PATH = "apps.system_intelligence.admin.chat.commands.ensure_context_summary"


class CompactProviderGateTests(ProviderStoreMixin, SystemIntelligenceAdminBase):
    def setUp(self):
        super().setUp()
        self.aws_config.delete()
        self.provider = make_provider()
        self.chat_config.default_provider = self.provider
        self.chat_config.default_model_id = "deepseek-chat"
        self.chat_config.save()
        for index in range(30):
            ChatMessage.objects.create(
                conversation=self.conversation,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
            )

    def _compact(self):
        return self.client.post(
            reverse("admin:system_intelligence_command", args=[self.conversation.id]),
            data=json.dumps({"command": "compact"}),
            content_type="application/json",
        )

    def test_provider_route_compacts_without_aws(self):
        with patch(SUMMARY_PATH, return_value=("summary", {"summarized_messages": 3})) as summarize:
            response = self._compact()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["compacted"])
        self.assertEqual(summarize.call_args.kwargs["chat_config"].default_provider, self.provider)
        self.assertEqual(summarize.call_args.kwargs["model_id"], "deepseek-chat")

    def test_disabled_provider_is_refused_with_fixed_text(self):
        self.provider.is_enabled = False
        self.provider.save()
        with patch(SUMMARY_PATH) as summarize:
            response = self._compact()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'The AI provider "DeepSeek" is disabled.')
        summarize.assert_not_called()

    def test_bedrock_route_without_aws_is_refused(self):
        self.chat_config.default_provider = None
        self.chat_config.save()
        with patch(SUMMARY_PATH) as summarize:
            response = self._compact()
        self.assertEqual(response.status_code, 400)
        self.assertIn("AWS credentials are not configured", response.json()["error"])
        summarize.assert_not_called()
