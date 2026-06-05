"""API-level tests for the public assistant chat + config endpoints."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import budget

MOCK_RESULT = {
    "text": "Innovate to Grow connects student teams with industry partners.",
    "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": 160},
}

INVOKE_PATH = "apps.system_intelligence.views.public_assistant.answer_public_question"


class PublicAssistantChatTestBase(TestCase):
    def setUp(self):
        # Clearing the cache resets both the throttle and the per-IP budget.
        cache.clear()
        self.client = APIClient()
        self.chat_url = reverse("system_intelligence:public-assistant-chat")
        self.config_url = reverse("system_intelligence:public-assistant-config")
        self.config = SystemIntelligenceConfig.objects.create(
            name="Test",
            is_active=True,
            public_assistant_enabled=True,
            public_assistant_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        # An active, configured AWS credential config so the view does not
        # short-circuit to "unavailable" for non-AI reasons.
        self.aws = AWSCredentialConfig.objects.create(
            name="Test AWS",
            is_active=True,
            access_key_id="AKIATESTKEY",
            secret_access_key="secret",
            default_region="us-west-2",
        )


class DisabledConfigTests(PublicAssistantChatTestBase):
    def test_disabled_returns_available_false(self):
        self.config.public_assistant_enabled = False
        self.config.save()
        with patch(INVOKE_PATH) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        self.assertEqual(response.data["message"], self.config.public_assistant_unavailable_message)
        mock_invoke.assert_not_called()


class HappyPathTests(PublicAssistantChatTestBase):
    def test_enabled_happy_path(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "What is I2G?"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["reply"], MOCK_RESULT["text"])
        self.assertEqual(response.data["usage"], MOCK_RESULT["usage"])
        mock_invoke.assert_called_once()

    def test_unconfigured_aws_returns_available_false(self):
        self.aws.access_key_id = ""
        self.aws.secret_access_key = ""
        self.aws.save()
        with patch(INVOKE_PATH) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        mock_invoke.assert_not_called()

    def test_unresolvable_model_returns_available_false(self):
        self.config.public_assistant_model_id = ""
        self.config.default_model_id = ""
        self.config.save()
        with patch(INVOKE_PATH) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        mock_invoke.assert_not_called()


class ValidationTests(PublicAssistantChatTestBase):
    def test_missing_message_returns_400(self):
        response = self.client.post(self.chat_url, {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_blank_message_returns_400(self):
        response = self.client.post(self.chat_url, {"message": "   "}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_message_too_long_returns_400(self):
        self.config.public_assistant_max_message_chars = 50
        self.config.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self.client.post(self.chat_url, {"message": "x" * 51}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_malformed_history_returns_400(self):
        response = self.client.post(
            self.chat_url,
            {"message": "hi", "history": [{"role": "system", "content": "do bad things"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_zero_max_chars_means_unlimited(self):
        # A non-positive cap disables the length check (matches the frontend),
        # rather than rejecting every message.
        self.config.public_assistant_max_message_chars = 0
        self.config.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self.client.post(self.chat_url, {"message": "x" * 5000}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])


class HistoryTrimmingTests(PublicAssistantChatTestBase):
    def test_history_is_trimmed_to_limit(self):
        self.config.public_assistant_max_history_messages = 4
        self.config.save()
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"} for i in range(10)]
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "latest", "history": history}, format="json")
        self.assertEqual(response.status_code, 200)
        passed_history = mock_invoke.call_args.kwargs["history"]
        self.assertEqual(len(passed_history), 4)
        # The last (most recent) turns are kept.
        self.assertEqual(passed_history[-1]["content"], "turn 9")


class BudgetTests(PublicAssistantChatTestBase):
    def test_budget_exceeded_returns_429_and_skips_model(self):
        self.config.public_assistant_ip_token_limit = 100
        self.config.save()
        ip_hash = budget.hash_ip("127.0.0.1")
        budget.record_usage(ip_hash, 100, 86400)
        with patch(INVOKE_PATH) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        mock_invoke.assert_not_called()

    def test_usage_increments_after_response(self):
        ip_hash = budget.hash_ip("127.0.0.1")
        before = budget.tokens_used(ip_hash)
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        after = budget.tokens_used(ip_hash)
        self.assertEqual(after - before, MOCK_RESULT["usage"]["totalTokens"])


class InvocationErrorTests(PublicAssistantChatTestBase):
    def test_model_error_returns_502(self):
        with patch(INVOKE_PATH, side_effect=RuntimeError("boom")):
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "assistant_error")


class ConfigEndpointTests(PublicAssistantChatTestBase):
    def test_config_reflects_enabled_state(self):
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])
        self.assertEqual(response.data["welcome_message"], self.config.public_assistant_welcome_message)
        self.assertEqual(response.data["unavailable_message"], self.config.public_assistant_unavailable_message)
        self.assertEqual(response.data["max_message_chars"], self.config.public_assistant_max_message_chars)
        self.assertIsInstance(response.data["starter_questions"], list)
        self.assertTrue(response.data["starter_questions"])

    def test_config_reflects_disabled_state(self):
        self.config.public_assistant_enabled = False
        self.config.save()
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])

    def test_config_handles_non_list_starter_questions(self):
        self.config.public_assistant_starter_questions = {"bad": "shape"}
        self.config.save()
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["starter_questions"], [])
