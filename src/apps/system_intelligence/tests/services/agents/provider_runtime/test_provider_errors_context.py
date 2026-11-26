"""Provider-aware error text and context management: fixed error templates (never ``str(exc)``), the provider's
context window in ``prepare_conversation_context``, and the provider passed to the context summarizer."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase
from litellm import exceptions as litellm_errors

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.models import ChatConversation, ChatMessage, SystemIntelligenceConfig
from apps.system_intelligence.services.agents import format_system_intelligence_error
from apps.system_intelligence.services.agents.context_manager import prepare_conversation_context
from apps.system_intelligence.services.agents.context_manager.summary import summarize_context_async
from apps.system_intelligence.services.agents.providers import ProviderConfigurationError

from .helpers import ProviderStoreMixin, make_provider

SECRET = "sk-echoed-secret https://internal.example"


def _auth_error():
    return litellm_errors.AuthenticationError(message=SECRET, llm_provider="openai", model="deepseek-chat")


class ProviderErrorFormattingTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.provider = make_provider()

    def fmt(self, error):
        return format_system_intelligence_error(error, aws_config=None, provider=self.provider)

    def test_authentication_error_maps_to_fixed_text(self):
        message = self.fmt(_auth_error())
        self.assertEqual(
            message, 'The AI provider "DeepSeek" rejected the API key. Install a valid key on the AI provider page.'
        )
        self.assertNotIn("sk-echoed", message)

    def test_error_found_in_the_cause_chain(self):
        try:
            try:
                raise litellm_errors.RateLimitError(message=SECRET, llm_provider="openai", model="m")
            except Exception as inner:
                raise RuntimeError("wrapper " + SECRET) from inner
        except RuntimeError as outer:
            message = self.fmt(outer)
        self.assertEqual(
            message, 'The AI provider "DeepSeek" reported a rate limit or exhausted quota. Try again later.'
        )

    def test_unknown_error_gets_generic_text_never_the_exception_text(self):
        message = self.fmt(RuntimeError(SECRET))
        self.assertEqual(
            message, 'The AI provider "DeepSeek" could not complete the request. See server logs for details.'
        )

    def test_configuration_error_and_plain_strings_pass_through(self):
        self.assertEqual(self.fmt(ProviderConfigurationError("Fixed config text.")), "Fixed config text.")
        self.assertEqual(self.fmt("Already formatted."), "Already formatted.")

    def test_bedrock_path_unchanged_without_provider(self):
        self.assertEqual(format_system_intelligence_error(RuntimeError("plain")), "plain")


class ProviderContextWindowTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = make_superuser()
        self.conversation = ChatConversation.objects.create(created_by=self.user)
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Hello")

    def _prepare(self, provider, model_id="deepseek-chat"):
        chat_config = SystemIntelligenceConfig(
            name="SI", is_active=True, default_provider=provider, default_model_id=model_id, system_prompt="p"
        )
        return prepare_conversation_context(
            self.conversation,
            list(self.conversation.messages.all()),
            chat_config=chat_config,
            aws_config=None,
            model_id=model_id,
            user_id=str(self.user.pk),
        )

    def test_configured_window_is_used(self):
        provider = make_provider(context_window_tokens=50_000)
        self.assertEqual(self._prepare(provider).usage["contextWindow"], 50_000)

    def test_litellm_model_list_is_used_when_window_is_zero(self):
        provider = make_provider()
        with patch("litellm.get_model_info", return_value={"max_input_tokens": 128_000}) as info:
            self.assertEqual(self._prepare(provider).usage["contextWindow"], 128_000)
        info.assert_called_with("deepseek-chat")

    def test_unknown_model_falls_back_to_default(self):
        provider = make_provider()
        with patch("litellm.get_model_info", side_effect=Exception("unmapped")):
            self.assertEqual(self._prepare(provider, "mystery").usage["contextWindow"], 64_000)

    def test_custom_provider_looks_up_bare_model_and_ignores_out_of_range_windows(self):
        provider = make_provider(name="Gateway", preset="custom", base_url="https://gateway.example.com/v1")
        with patch("litellm.get_model_info", return_value={"max_input_tokens": 999}) as info:
            self.assertEqual(self._prepare(provider, "my-model").usage["contextWindow"], 64_000)
        info.assert_called_once_with("my-model")

    def test_bedrock_heuristic_without_provider(self):
        prepared = self._prepare(None, "us.anthropic.claude-opus-4-20250514-v1:0")
        self.assertEqual(prepared.usage["contextWindow"], 200_000)


class ProviderSummaryTests(ProviderStoreMixin, TestCase):
    def test_summary_call_uses_default_provider(self):
        provider = make_provider()
        chat_config = SystemIntelligenceConfig(
            name="SI", default_provider=provider, default_model_id="deepseek-chat", temperature=0.4
        )
        fake = AsyncMock(return_value=MagicMock(text=" Summary "))
        with patch("apps.system_intelligence.services.agents.context_manager.summary.run_tool_free_agent_async", fake):
            summary = asyncio.run(
                summarize_context_async(
                    existing_summary="",
                    new_context="ctx",
                    chat_config=chat_config,
                    aws_config=None,
                    model_id="deepseek-chat",
                    user_id="u",
                )
            )
        self.assertEqual(summary, "Summary")
        kwargs = fake.call_args.kwargs
        self.assertEqual(kwargs["provider"], provider)
        self.assertIsNone(kwargs["aws_config"])
        self.assertEqual(kwargs["temperature"], 0.4)
