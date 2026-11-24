"""Custom endpoint providers get an HTTP client that refuses redirects, and a refused redirect has fixed text."""

import asyncio
from unittest.mock import patch

import httpx
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from litellm import exceptions as litellm_exceptions
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler
from openai import AsyncOpenAI

from apps.core.services.credential_store import memory
from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.services.agents.definition.litellm import build_litellm_model
from apps.system_intelligence.services.agents.providers.error_messages import (
    describe_provider_error,
    provider_error_message,
)
from apps.system_intelligence.services.agents.providers.http_clients import (
    REDIRECT_REFUSED,
    RedirectRefused,
    no_redirect_client,
    no_redirect_model,
    refuse_redirects,
)
from apps.system_intelligence.services.agents.providers.keys import install_api_key
from apps.system_intelligence.services.agents.providers.litellm_args import provider_call_args

from . import make_provider

API_KEY = "fake-fake-fake-1234"
GATEWAY = "https://gateway.example.com/v1"
Preset = LLMProviderConfig.Preset
SOCKET = "apps.system_intelligence.services.agents.providers.endpoints.socket.getaddrinfo"
PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]


def _custom(api_format, **fields):
    return LLMProviderConfig(preset=Preset.CUSTOM, api_format=api_format, base_url=GATEWAY, **fields)


def _redirecting_transport(requested):
    """A transport that answers every request with ``307 Location: http://10.0.0.5/`` and records the URLs."""

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(307, headers={"Location": "http://10.0.0.5/steal"})

    return httpx.MockTransport(handler)


class RefuseRedirectsHookTests(SimpleTestCase):
    def test_every_3xx_raises(self):
        for status in (300, 301, 302, 307, 308, 399):
            with self.subTest(status=status), self.assertRaisesMessage(RedirectRefused, REDIRECT_REFUSED):
                asyncio.run(refuse_redirects(httpx.Response(status)))

    def test_other_statuses_pass(self):
        for status in (200, 201, 299, 400, 401, 500):
            with self.subTest(status=status):
                self.assertIsNone(asyncio.run(refuse_redirects(httpx.Response(status))))


class NoRedirectClientTests(SimpleTestCase):
    def test_anthropic_format_gets_an_http_handler_with_the_hook(self):
        client = no_redirect_client(_custom("anthropic", request_timeout_seconds=33), api_key=API_KEY, base_url=GATEWAY)
        self.assertIsInstance(client, AsyncHTTPHandler)
        self.assertEqual(client.client.event_hooks["response"], [refuse_redirects])
        self.assertEqual(client.client.timeout, httpx.Timeout(33))

    def test_openai_format_gets_an_openai_client_that_does_not_follow_redirects(self):
        client = no_redirect_client(_custom("openai", request_timeout_seconds=33), api_key=API_KEY, base_url=GATEWAY)
        self.assertIsInstance(client, AsyncOpenAI)
        self.assertEqual((str(client.base_url), client.api_key, client.timeout), (f"{GATEWAY}/", API_KEY, 33))
        self.assertEqual(client._client.event_hooks["response"], [refuse_redirects])
        self.assertFalse(client._client.follow_redirects)

    def test_redirect_target_is_never_requested(self):
        # LiteLLM's AsyncHTTPHandler client follows redirects by default: the hook must stop it first.
        requested = []
        handler = no_redirect_client(_custom("anthropic"), api_key=API_KEY, base_url=GATEWAY)
        self.assertTrue(handler.client.follow_redirects)
        handler.client._transport = _redirecting_transport(requested)

        async def post():
            try:
                await handler.client.post(f"{GATEWAY}/messages", json={})
            finally:
                await handler.client.aclose()

        with self.assertRaisesMessage(RedirectRefused, REDIRECT_REFUSED):
            asyncio.run(post())
        self.assertEqual(requested, [f"{GATEWAY}/messages"])


@override_settings(CREDENTIAL_STORE_BACKEND="memory", CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=False)
class ProviderCallArgsClientTests(TestCase):
    def setUp(self):
        cache.clear()
        memory.reset()
        self.addCleanup(memory.reset)

    def _keyed(self, **fields):
        provider = make_provider(**fields)
        install_api_key(provider, API_KEY)
        provider.is_enabled = True
        return provider

    def test_preset_gets_only_the_timeout(self):
        provider = self._keyed(request_timeout_seconds=21)
        self.assertEqual(provider_call_args(provider), {"timeout": 21})

    def test_custom_endpoint_gets_the_no_redirect_model_and_a_fresh_client_per_request(self):
        provider = self._keyed(name="Gateway", preset=Preset.CUSTOM, base_url=GATEWAY, request_timeout_seconds=21)
        with patch(SOCKET, return_value=PUBLIC_ADDRINFO):
            model = build_litellm_model(aws_config=None, model_id="m", provider=provider)
        self.assertEqual(type(model).__name__, "NoRedirectLitellmModel")
        self.assertEqual(provider_call_args(provider), {"timeout": 21})
        seen = []

        async def fake_fetch(_self, system_instructions, input, model_settings, *args, **kwargs):
            seen.append(model_settings.extra_args)

        settings = ModelSettings(max_tokens=5, extra_args={"timeout": 21})
        with patch(f"{LitellmModel.__module__}.LitellmModel._fetch_response", fake_fetch):
            asyncio.run(model._fetch_response("s", "hi", settings))
            asyncio.run(model._fetch_response("s", "hi", settings))
        clients = [args["client"] for args in seen]
        self.assertIsInstance(clients[0], AsyncOpenAI)
        self.assertIsNot(clients[0], clients[1])
        self.assertEqual((clients[0].api_key, str(clients[0].base_url)), (API_KEY, f"{GATEWAY}/"))
        self.assertEqual(settings.extra_args, {"timeout": 21})  # the caller's settings are not mutated

    def test_custom_anthropic_endpoint_requests_use_an_http_handler(self):
        provider = self._keyed(name="Gateway", preset=Preset.CUSTOM, api_format="anthropic", base_url=GATEWAY)
        model = no_redirect_model(provider, model="anthropic/m", base_url=GATEWAY, api_key=API_KEY)
        seen = []

        async def fake_fetch(_self, system_instructions, input, model_settings, *args, **kwargs):
            seen.append(model_settings.extra_args["client"])

        with patch(f"{LitellmModel.__module__}.LitellmModel._fetch_response", fake_fetch):
            asyncio.run(model._fetch_response("s", "hi", ModelSettings(max_tokens=5)))
        self.assertIsInstance(seen[0], AsyncHTTPHandler)

    def test_preset_provider_gets_the_plain_litellm_model(self):
        provider = self._keyed()
        self.assertIs(type(build_litellm_model(aws_config=None, model_id="m", provider=provider)), LitellmModel)


class RedirectErrorMessageTests(SimpleTestCase):
    def test_refused_redirect_maps_to_its_text(self):
        self.assertEqual(describe_provider_error(RedirectRefused(REDIRECT_REFUSED), "Gateway"), REDIRECT_REFUSED)

    def test_refused_redirect_inside_a_litellm_error_is_recognised_by_its_text(self):
        # LiteLLM re-raises the hook's error as an APIConnectionError that only keeps its message.
        wrapped = litellm_exceptions.APIConnectionError(
            message=f"AnthropicException - {REDIRECT_REFUSED}", llm_provider="anthropic", model="m"
        )
        self.assertEqual(describe_provider_error(wrapped, "Gateway"), REDIRECT_REFUSED)
        self.assertEqual(provider_error_message(wrapped, "Gateway"), REDIRECT_REFUSED)

    def test_refused_redirect_in_the_cause_chain_is_found(self):
        outer = RuntimeError("agent run failed")
        outer.__cause__ = RedirectRefused(REDIRECT_REFUSED)
        self.assertEqual(provider_error_message(outer, "Gateway"), REDIRECT_REFUSED)
