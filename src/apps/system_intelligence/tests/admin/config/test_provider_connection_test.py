"""The AI provider "Test connection" admin action. The model call is always patched."""

from unittest.mock import patch

from django.contrib.messages import get_messages

from apps.system_intelligence.admin.config.provider_keys import PROBE_PROMPT
from apps.system_intelligence.services.agents.invocation.runner import AgentTextResult
from apps.system_intelligence.tests.admin.config.test_provider_admin import (
    RUN_PROBE,
    TEST_KEY,
    ProviderAdminTestCase,
    action_url,
    change_url,
    make_provider,
)

GENERIC_FAILURE = "Test failed: The AI provider 'DeepSeek' could not complete the request. See server logs for details."


def _messages(response):
    return [(message.level_tag, str(message)) for message in get_messages(response.wsgi_request)]


class TestConnectionActionTests(ProviderAdminTestCase):
    def setUp(self):
        super().setUp()
        self.provider = make_provider(key=TEST_KEY)
        self.url = action_url("test_connection_action", self.provider)

    def _post(self, model_id="deepseek-chat", **probe):
        with patch(RUN_PROBE, **probe) as run:
            response = self.client.post(self.url, {"model_id": model_id})
        self.assertRedirects(response, change_url(self.provider), fetch_redirect_response=False)
        return response, run

    def test_get_prefills_the_first_suggested_model(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test connection: DeepSeek")
        self.assertContains(response, 'value="deepseek-chat"')
        self.assertContains(response, '<option value="deepseek-reasoner">deepseek-reasoner</option>')
        self.assertContains(response, "Send test request")

    def test_get_for_a_custom_endpoint_has_no_suggestion(self):
        custom = make_provider(name="Gateway", preset="custom", base_url="https://gateway.example.com/v1")
        response = self.client.get(action_url("test_connection_action", custom))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial, {})
        self.assertContains(response, "<datalist")

    def test_success_reports_the_reply_and_tokens(self):
        result = AgentTextResult(text="  OK  ", usage={"totalTokens": 7})
        response, run = self._post(model_id="  deepseek-chat  ", return_value=result)
        self.assertEqual(_messages(response), [("success", 'Test passed. deepseek-chat replied: "OK" (7 tokens).')])
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["model_id"], "deepseek-chat")
        self.assertEqual(kwargs["input_data"], PROBE_PROMPT)
        self.assertIsNone(kwargs["aws_config"])
        self.assertEqual(kwargs["max_tokens"], 16)
        self.assertFalse(kwargs["include_temperature"])
        self.assertEqual(kwargs["agent_name"], "system_intelligence_provider_test")
        # The probe may run while the provider is still disabled; the saved row stays disabled.
        self.assertEqual(kwargs["provider"].pk, self.provider.pk)
        self.assertTrue(kwargs["provider"].is_enabled)
        self.provider.refresh_from_db()
        self.assertFalse(self.provider.is_enabled)

    def test_missing_usage_reports_zero_tokens_and_long_reply_is_truncated(self):
        result = AgentTextResult(text="x" * 200, usage={})
        response, _run = self._post(return_value=result)
        self.assertEqual(
            _messages(response), [("success", f'Test passed. deepseek-chat replied: "{"x" * 80}" (0 tokens).')]
        )

    def test_empty_reply_is_a_warning(self):
        response, _run = self._post(return_value=AgentTextResult(text="   ", usage={"totalTokens": 3}))
        self.assertEqual(
            _messages(response), [("warning", "deepseek-chat answered with no text; check its output token limit.")]
        )

    def test_none_reply_is_a_warning(self):
        response, _run = self._post(return_value=AgentTextResult(text=None, usage={}))
        self.assertEqual(_messages(response)[0][0], "warning")

    def test_unknown_exception_shows_fixed_text_only(self):
        error = RuntimeError("upstream said sk-secret at https://internal.example")
        with self.assertLogs("apps.system_intelligence.admin.config.provider_keys", level="WARNING"):
            response, _run = self._post(side_effect=error)
        self.assertEqual(_messages(response), [("error", GENERIC_FAILURE)])

    def test_litellm_authentication_error_maps_to_its_template(self):
        from litellm.exceptions import AuthenticationError

        error = AuthenticationError("bad key sk-secret", llm_provider="openai", model="deepseek-chat")
        with self.assertLogs("apps.system_intelligence.admin.config.provider_keys", level="WARNING"):
            response, _run = self._post(side_effect=error)
        level, text = _messages(response)[0]
        self.assertEqual(level, "error")
        self.assertEqual(
            text,
            "Test failed: The AI provider 'DeepSeek' rejected the API key. Install a valid key on the AI provider page.",
        )
        self.assertNotIn("sk-secret", text)

    def test_refuses_without_an_installed_key(self):
        self.provider.key_secret_ref = self.provider.key_version_id = ""
        self.provider.save()
        response, run = self._post()
        run.assert_not_called()
        self.assertEqual(_messages(response), [("error", "Install an API key first.")])

    def test_blank_model_rerenders_the_form(self):
        with patch(RUN_PROBE) as run:
            response = self.client.post(self.url, {"model_id": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("model_id", response.context["form"].errors)
        run.assert_not_called()
