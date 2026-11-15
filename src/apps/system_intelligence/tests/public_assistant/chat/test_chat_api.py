"""API-level tests for the public assistant chat + config endpoints."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import (
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant.chat import actors

MOCK_RESULT = {
    "text": "Innovate to Grow connects student teams with industry partners.",
    "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": 160},
}

# Mocks that must NOT be called still return MOCK_RESULT: a bare MagicMock reaching
# the JSON renderer makes a regression hang the run instead of failing an assertion.
INVOKE_PATH = "apps.system_intelligence.views.chat_turn.answer_public_question"


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
class PublicAssistantChatTestBase(TestCase):
    def setUp(self):
        # Clearing the cache resets both the throttle and the token budgets.
        cache.clear()
        # These requests carry no visitor value, so they are all charged to the
        # shared legacy bucket (never to the client IP).
        self.legacy_key = actors.legacy_actor().key
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
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
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
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        mock_invoke.assert_not_called()

    def test_unresolvable_model_returns_available_false(self):
        self.config.public_assistant_model_id = ""
        self.config.default_model_id = ""
        self.config.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
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

    def test_history_item_uses_message_character_limit(self):
        self.config.public_assistant_max_message_chars = 50
        self.config.save()
        response = self.client.post(
            self.chat_url,
            {
                "message": "hi",
                "history": [{"role": "user", "content": "x" * 51}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_history_item_count_is_bounded_before_child_validation(self):
        history = [{"role": "user", "content": "x"} for _ in range(101)]
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(
                self.chat_url,
                {"message": "hi", "history": history},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        mock_invoke.assert_not_called()

    def test_estimated_input_limit_rejects_before_model_call(self):
        self.config.public_assistant_max_estimated_input_tokens = 5
        self.config.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(
                self.chat_url,
                {"message": "This request is larger than five estimated tokens."},
                format="json",
            )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["code"], "input_too_large")
        mock_invoke.assert_not_called()

    def test_zero_max_chars_means_unlimited(self):
        # A non-positive cap disables the length check (matches the frontend),
        # rather than rejecting every message.
        self.config.public_assistant_max_message_chars = 0
        self.config.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self.client.post(self.chat_url, {"message": "x" * 5000}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])


SESSION = "44444444-4444-4444-4444-444444444444"
