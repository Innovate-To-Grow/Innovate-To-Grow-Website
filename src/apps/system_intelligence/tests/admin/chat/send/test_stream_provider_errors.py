"""``_stream_exception`` turns an API-key provider failure into fixed SSE text, never the exception's own text.

Provider text is used only when the chat config routes to a provider; a Bedrock-only deployment keeps the generic
message even for a LiteLLM error.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from litellm import exceptions as litellm_errors

from apps.system_intelligence.admin.stream.async_events import _async_event_stream
from apps.system_intelligence.admin.stream.helpers import _GENERIC_STREAM_ERROR, _stream_exception
from apps.system_intelligence.admin.stream.sync_events import _event_stream
from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.services.agents.providers import ProviderConfigurationError
from apps.system_intelligence.services.agents.providers.http_clients import REDIRECT_REFUSED, RedirectRefused

LOGGER = "apps.system_intelligence.admin.stream.helpers"
SECRET = "Incorrect API key provided: sk-leak****1234"
REJECTED_KEY = 'The AI provider "DeepSeek" rejected the API key. Install a valid key on the AI provider page.'


def _error_payload(sse: str) -> str:
    event_line, data_line = sse.strip().split("\n")
    assert event_line == "event: error"
    return json.loads(data_line.removeprefix("data: "))["error"]


def _auth_error():
    return litellm_errors.AuthenticationError(message=SECRET, llm_provider="openai", model="deepseek-chat")


class StreamExceptionProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = LLMProviderConfig(name="DeepSeek", preset=LLMProviderConfig.Preset.DEEPSEEK)

    def _message(self, exc, provider):
        with self.assertLogs(LOGGER, level="ERROR"):
            return _error_payload(_stream_exception("conv-1", exc, None, provider))

    def test_litellm_authentication_error_maps_to_fixed_text(self):
        message = self._message(_auth_error(), self.provider)
        self.assertEqual(message, REJECTED_KEY)
        self.assertNotIn("sk-leak", message)

    def test_wrapped_not_found_error_is_found_in_the_chain(self):
        inner = litellm_errors.NotFoundError(message=SECRET, llm_provider="anthropic", model="x")
        outer = RuntimeError("agent run failed")
        outer.__cause__ = inner
        message = self._message(outer, self.provider)
        self.assertEqual(message, 'The AI provider "DeepSeek" does not serve this model. Check the model name.')

    def test_provider_configuration_error_text_is_shown(self):
        exc = ProviderConfigurationError('The AI provider "DeepSeek" is disabled.')
        self.assertEqual(self._message(exc, self.provider), 'The AI provider "DeepSeek" is disabled.')

    def test_refused_redirect_has_its_own_text(self):
        self.assertEqual(self._message(RedirectRefused(REDIRECT_REFUSED), self.provider), REDIRECT_REFUSED)

    def test_other_errors_stay_generic(self):
        self.assertEqual(self._message(RuntimeError(SECRET), self.provider), _GENERIC_STREAM_ERROR)

    def test_without_a_provider_litellm_errors_stay_generic(self):
        for exc in (_auth_error(), ProviderConfigurationError("fixed"), RuntimeError(SECRET)):
            with self.subTest(exc=type(exc).__name__):
                message = self._message(exc, None)
                self.assertEqual(message, _GENERIC_STREAM_ERROR)
                self.assertNotIn("sk-leak", message)


class EventStreamPassesTheProviderTests(SimpleTestCase):
    """Both stream variants hand ``chat_config.default_provider`` to ``_stream_exception``."""

    def setUp(self):
        self.request = SimpleNamespace(user=SimpleNamespace(pk="user-1"))
        self.convo = SimpleNamespace(id="conv-1", pk="conv-1")

    def _sync_error(self, chat_config):
        with (
            patch("apps.system_intelligence.admin.stream.sync_events.prepare_conversation_context") as prepare,
            self.assertLogs(LOGGER, level="ERROR"),
        ):
            prepare.side_effect = _auth_error()
            payloads = list(_event_stream(self.request, self.convo, [], chat_config, None, "deepseek-chat"))
        self.assertEqual(len(payloads), 2)  # start, then the error
        return _error_payload(payloads[-1])

    def _async_error(self, chat_config):
        async def collect():
            stream = _async_event_stream(self.request, self.convo, [], chat_config, None, "deepseek-chat")
            return [payload async for payload in stream]

        with (
            patch("apps.system_intelligence.admin.stream.async_events.prepare_conversation_context") as prepare,
            self.assertLogs(LOGGER, level="ERROR"),
        ):
            prepare.side_effect = _auth_error()
            payloads = [payload for payload in asyncio.run(collect()) if payload.startswith("event: error")]
        self.assertEqual(len(payloads), 1)
        return _error_payload(payloads[0])

    def test_provider_routed_config_gets_provider_text(self):
        config = SimpleNamespace(default_provider=LLMProviderConfig(name="DeepSeek"))
        self.assertEqual(self._sync_error(config), REJECTED_KEY)
        self.assertEqual(self._async_error(config), REJECTED_KEY)

    def test_bedrock_config_gets_the_generic_text(self):
        for config in (SimpleNamespace(default_provider=None), SimpleNamespace()):
            with self.subTest(config=config):
                self.assertEqual(self._sync_error(config), _GENERIC_STREAM_ERROR)
                self.assertEqual(self._async_error(config), _GENERIC_STREAM_ERROR)
