import sys
import types
from unittest.mock import patch

import httpx
from django.core.cache import cache
from django.test import SimpleTestCase
from litellm import exceptions as litellm_exceptions

from apps.system_intelligence.services.agents.providers.error_messages import (
    GENERIC,
    describe_provider_error,
    provider_error_message,
)
from apps.system_intelligence.services.agents.providers.routing import ProviderConfigurationError

LABEL = "My Gateway"
UNAVAILABLE = f"{LABEL} is temporarily unavailable. Try again later."


def _litellm_error(name):
    cls = getattr(litellm_exceptions, name)
    kwargs = {"message": "sk-secret leaked https://internal", "llm_provider": "openai", "model": "gpt-4o"}
    if name == "PermissionDeniedError":
        kwargs["response"] = httpx.Response(403, request=httpx.Request("POST", "https://example.com"))
    return cls(**kwargs)


EXPECTED = {
    "ContextWindowExceededError": "The conversation is too long for this model's context window. Start a new chat "
    "or run /compact.",
    "AuthenticationError": f"{LABEL} rejected the API key. Install a valid key on the AI provider page.",
    "PermissionDeniedError": f"{LABEL} refused access to this model.",
    "NotFoundError": f"{LABEL} does not serve this model. Check the model name.",
    "RateLimitError": f"{LABEL} reported a rate limit or exhausted quota. Try again later.",
    "Timeout": f"{LABEL} did not answer in time.",
    "APIConnectionError": f"Unable to reach {LABEL}. Check network connectivity for the server and try again.",
    "ServiceUnavailableError": UNAVAILABLE,
    "InternalServerError": UNAVAILABLE,
    "BadGatewayError": UNAVAILABLE,
    "BadRequestError": f"{LABEL} rejected the request. Check the model name and settings.",
}


class DescribeProviderErrorTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_each_litellm_exception_maps_to_fixed_text(self):
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                error = _litellm_error(name)
                self.assertEqual(describe_provider_error(error, LABEL), expected)
                message = provider_error_message(error, LABEL)
                self.assertEqual(message, expected)
                self.assertNotIn("sk-secret", message)

    def test_subclasses_match_before_their_bases(self):
        context = _litellm_error("ContextWindowExceededError")
        self.assertIsInstance(context, litellm_exceptions.BadRequestError)
        self.assertEqual(describe_provider_error(context, LABEL), EXPECTED["ContextWindowExceededError"])
        self.assertEqual(describe_provider_error(_litellm_error("Timeout"), LABEL), EXPECTED["Timeout"])

    def test_bad_request_subclass_without_own_template_uses_bad_request_text(self):
        error = litellm_exceptions.ContentPolicyViolationError(message="x", model="m", llm_provider="openai")
        self.assertEqual(describe_provider_error(error, LABEL), EXPECTED["BadRequestError"])

    def test_explicitly_chained_cause_is_found(self):
        try:
            try:
                raise _litellm_error("AuthenticationError")
            except Exception as exc:
                raise RuntimeError("wrapper") from exc
        except RuntimeError as wrapper:
            self.assertEqual(describe_provider_error(wrapper, LABEL), EXPECTED["AuthenticationError"])

    def test_implicit_context_is_found(self):
        try:
            try:
                raise _litellm_error("RateLimitError")
            except Exception:
                raise ValueError("while handling")  # noqa: B904 - the implicit __context__ is what is tested
        except ValueError as wrapper:
            self.assertEqual(describe_provider_error(wrapper, LABEL), EXPECTED["RateLimitError"])

    def test_outermost_known_error_wins(self):
        outer = _litellm_error("NotFoundError")
        outer.__cause__ = _litellm_error("AuthenticationError")
        self.assertEqual(describe_provider_error(outer, LABEL), EXPECTED["NotFoundError"])

    def test_provider_configuration_error_passes_through(self):
        error = ProviderConfigurationError('The AI provider "X" is disabled.')
        self.assertEqual(describe_provider_error(error, LABEL), 'The AI provider "X" is disabled.')
        wrapper = RuntimeError("outer")
        wrapper.__cause__ = error
        self.assertEqual(provider_error_message(wrapper, LABEL), 'The AI provider "X" is disabled.')

    def test_unknown_errors_and_cycles(self):
        self.assertIsNone(describe_provider_error(RuntimeError("boom"), LABEL))
        first, second = RuntimeError("a"), RuntimeError("b")
        first.__cause__, second.__cause__ = second, first
        self.assertIsNone(describe_provider_error(first, LABEL))
        generic = litellm_exceptions.APIError(status_code=500, message="x", llm_provider="openai", model="m")
        self.assertEqual(provider_error_message(generic, LABEL), GENERIC.format(label=LABEL))
        self.assertEqual(
            provider_error_message(first, LABEL),
            "My Gateway could not complete the request. See server logs for details.",
        )

    def test_string_passes_through(self):
        self.assertEqual(provider_error_message("Already formatted.", LABEL), "Already formatted.")

    def test_litellm_unavailable_falls_back_to_generic(self):
        with patch.dict(sys.modules, {"litellm": None}):
            self.assertIsNone(describe_provider_error(_litellm_error("AuthenticationError"), LABEL))
            self.assertEqual(provider_error_message(RuntimeError("x"), LABEL), GENERIC.format(label=LABEL))
        # ProviderConfigurationError needs no LiteLLM.
        with patch.dict(sys.modules, {"litellm": None}):
            self.assertEqual(describe_provider_error(ProviderConfigurationError("fixed"), LABEL), "fixed")

    def test_missing_exception_names_are_skipped(self):
        class FakeRateLimit(Exception):
            pass

        fake = types.ModuleType("litellm")
        fake.exceptions = types.SimpleNamespace(RateLimitError=FakeRateLimit, Timeout="not-a-class")
        with patch.dict(sys.modules, {"litellm": fake}):
            self.assertEqual(describe_provider_error(FakeRateLimit(), LABEL), EXPECTED["RateLimitError"])
            self.assertIsNone(describe_provider_error(RuntimeError(), LABEL))
