"""The public assistant on an API-key provider: ``answer_public_question`` passes the public route's provider, and
the chat endpoint is available with a usable provider and no AWS, unavailable when the provider is disabled or
keyless, and audits ``<preset>/<model>`` as the model id."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.bedrock import BedrockError
from apps.system_intelligence.services.public_assistant.chat import invoke
from apps.system_intelligence.tests.services.agents.provider_runtime.helpers import ProviderStoreMixin, make_provider

AGENT_PATH = "apps.system_intelligence.services.public_assistant.chat.invoke.run_tool_free_agent"
INVOKE_PATH = "apps.system_intelligence.views.chat_turn.answer_public_question"
MOCK_RESULT = {"text": "Hello from DeepSeek.", "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}}


def _result():
    return MagicMock(text="ok", usage={"inputTokens": 1, "outputTokens": 1, "totalTokens": 2})


class AnswerPublicQuestionProviderTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.provider = make_provider()

    def _answer(self, config):
        return invoke.answer_public_question(message="hi", history=[], config=config, context="ctx")

    def test_public_provider_and_model_are_passed(self):
        config = SystemIntelligenceConfig(
            name="SI",
            public_assistant_provider=self.provider,
            public_assistant_model_id="  deepseek-chat ",
            public_assistant_temperature=0.3,
        )
        with patch(AGENT_PATH, return_value=_result()) as agent:
            self.assertEqual(self._answer(config)["text"], "ok")
        kwargs = agent.call_args.kwargs
        self.assertEqual(kwargs["provider"], self.provider)
        self.assertEqual(kwargs["model_id"], "deepseek-chat")
        self.assertEqual(kwargs["temperature"], 0.3)

    def test_blank_public_model_falls_back_to_default_provider(self):
        config = SystemIntelligenceConfig(
            name="SI", default_provider=self.provider, default_model_id="deepseek-reasoner"
        )
        with patch(AGENT_PATH, return_value=_result()) as agent:
            self._answer(config)
        self.assertEqual(agent.call_args.kwargs["provider"], self.provider)
        self.assertEqual(agent.call_args.kwargs["model_id"], "deepseek-reasoner")

    def test_temperature_retry_keeps_the_provider(self):
        config = SystemIntelligenceConfig(
            name="SI", public_assistant_provider=self.provider, public_assistant_model_id="deepseek-chat"
        )
        with patch(AGENT_PATH, side_effect=[Exception("Invalid temperature"), _result()]) as agent:
            self._answer(config)
        first, second = agent.call_args_list
        self.assertEqual(first.kwargs["provider"], self.provider)
        self.assertEqual(second.kwargs["provider"], self.provider)
        self.assertFalse(second.kwargs["include_temperature"])

    def test_failed_retry_raises_bedrock_error(self):
        config = SystemIntelligenceConfig(
            name="SI", public_assistant_provider=self.provider, public_assistant_model_id="deepseek-chat"
        )
        effects = [Exception("Invalid temperature"), RuntimeError("still failing")]
        with patch(AGENT_PATH, side_effect=effects), self.assertLogs(invoke.logger, level="ERROR"):
            with self.assertRaises(BedrockError):
                self._answer(config)


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
class PublicChatEndpointProviderTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.url = reverse("system_intelligence:public-assistant-chat")
        self.provider = make_provider()
        # No AWSCredentialConfig row at all: the provider route must not need one.
        self.config = SystemIntelligenceConfig.objects.create(
            name="SI",
            is_active=True,
            public_assistant_enabled=True,
            public_assistant_provider=self.provider,
            public_assistant_model_id="deepseek-chat",
        )

    def _post(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as answer:
            response = self.client.post(self.url, {"message": "What is I2G?"}, format="json")
        return response, answer

    def test_available_with_provider_and_no_aws(self):
        self.assertFalse(AWSCredentialConfig.load().is_configured)
        response, answer = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["reply"], MOCK_RESULT["text"])
        answer.assert_called_once()
        log = AssistantMessageLog.objects.get()
        self.assertEqual(log.model_id, "deepseek/deepseek-chat")
        self.assertEqual(log.status, AssistantMessageLog.STATUS_OK)

    def test_disabled_provider_reports_unavailable(self):
        self.provider.is_enabled = False
        self.provider.save()
        response, answer = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        answer.assert_not_called()
        log = AssistantMessageLog.objects.get()
        self.assertEqual(log.status, AssistantMessageLog.STATUS_UNAVAILABLE)
        self.assertEqual(log.model_id, "deepseek/deepseek-chat")

    def test_keyless_provider_reports_unavailable(self):
        keyless = make_provider(name="Kimi", preset="moonshot", with_key=False, enabled=False)
        keyless.is_enabled = True  # enabled without a key (bypassing clean): still never called
        keyless.save()
        self.config.public_assistant_provider = keyless
        self.config.public_assistant_model_id = "kimi-latest"
        self.config.save()
        response, answer = self._post()
        self.assertFalse(response.data["available"])
        answer.assert_not_called()
        self.assertEqual(AssistantMessageLog.objects.get().model_id, "moonshot/kimi-latest")
