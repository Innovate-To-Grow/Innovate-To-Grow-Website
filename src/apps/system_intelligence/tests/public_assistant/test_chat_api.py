"""API-level tests for the public assistant chat + config endpoints."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    PublicAssistantTokenBudget,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import actors, budget

MOCK_RESULT = {
    "text": "Innovate to Grow connects student teams with industry partners.",
    "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": 160},
}

# Mocks that must NOT be called still return MOCK_RESULT: a bare MagicMock reaching
# the JSON renderer makes a regression hang the run instead of failing an assertion.
INVOKE_PATH = "apps.system_intelligence.views.public_assistant.answer_public_question"


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

    def test_total_history_chars_trim_oldest_turns(self):
        self.config.public_assistant_max_history_chars = 12
        self.config.public_assistant_max_history_messages = 10
        self.config.save()
        history = [
            {"role": "user", "content": "old-old"},
            {"role": "assistant", "content": "middle"},
            {"role": "user", "content": "newest"},
        ]
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(
                self.chat_url,
                {"message": "latest", "history": history},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_invoke.call_args.kwargs["history"],
            history[-2:],
        )


class BudgetTests(PublicAssistantChatTestBase):
    def test_budget_exceeded_returns_429_and_skips_model(self):
        self.config.public_assistant_ip_token_limit = 100
        self.config.save()
        visitor = self.client.get(self.config_url).data["visitor_token"]
        budget.record_usage(actors.visitor_actor(visitor).key, 100, 86400)
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(
                self.chat_url,
                {"message": "hi", "visitor_token": visitor},
                format="json",
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        # The limit may be a shared one, so the copy must not blame the asker.
        self.assertEqual(
            response.data["detail"],
            "The assistant has reached its usage limit for now. Please try again later.",
        )
        mock_invoke.assert_not_called()

    def test_requests_without_a_visitor_value_are_not_held_to_the_per_visitor_limit(self):
        # The shared legacy actor is many people at once: only the assistant's
        # global budget (and its request throttle) bound it.
        self.config.public_assistant_ip_token_limit = 100
        self.config.save()
        budget.record_usage(self.legacy_key, 100, 86400)
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        mock_invoke.assert_called_once()
        self.assertEqual(budget.tokens_used(self.legacy_key), 100 + MOCK_RESULT["usage"]["totalTokens"])

    def test_usage_increments_after_response(self):
        before = budget.tokens_used(self.legacy_key)
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 200)
        after = budget.tokens_used(self.legacy_key)
        self.assertEqual(after - before, MOCK_RESULT["usage"]["totalTokens"])
        # Every chat turn is also charged to the assistant's global budget,
        # and never to AI search's.
        self.assertEqual(budget.global_tokens_used(budget.FEATURE_ASSISTANT), MOCK_RESULT["usage"]["totalTokens"])
        self.assertEqual(budget.global_tokens_used(budget.FEATURE_AI_SEARCH), 0)

    def test_a_usage_block_that_is_not_plain_integers_is_never_echoed_or_a_500(self):
        """The provider's usage block is outside our control: NaN cannot even be serialised as JSON."""
        odd_blocks = (
            {"inputTokens": float("nan"), "outputTokens": float("inf"), "totalTokens": float("nan")},
            {"inputTokens": "12", "outputTokens": [3], "totalTokens": "x"},
            {"inputTokens": 5, "outputTokens": 7, "totalTokens": 10**30},
            {"inputTokens": -4, "outputTokens": True, "totalTokens": None},
            ["not", "a", "mapping"],
            "garbage",
        )
        for usage in odd_blocks:
            with self.subTest(usage=repr(usage)[:60]):
                cache.clear()
                with patch(INVOKE_PATH, return_value={"text": "Hello.", "usage": usage}):
                    response = self.client.post(self.chat_url, {"message": "hi"}, format="json")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["reply"], "Hello.")
                for key, value in response.data["usage"].items():
                    self.assertIn(key, ("inputTokens", "outputTokens", "totalTokens"))
                    self.assertIs(type(value), int)
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, budget.MAX_REPORTED_TOKENS)

    def test_a_readable_usage_block_is_returned_unchanged(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")

        self.assertEqual(response.data["usage"], MOCK_RESULT["usage"])

    def test_client_ip_keys_no_budget(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            self.client.post(self.chat_url, {"message": "hi"}, format="json", REMOTE_ADDR="198.51.100.77")
        self.assertEqual(budget.tokens_used(budget.hash_ip("198.51.100.77")), 0)

    @override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="redis://configured")
    @patch(
        "apps.system_intelligence.services.public_assistant.budget._shared_redis_client",
        side_effect=budget.BudgetBackendUnavailable("redis down"),
    )
    def test_redis_failure_returns_graceful_503(self, _redis):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        mock_invoke.assert_not_called()

    @override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
    def test_missing_redis_uses_the_shared_database_budget(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        mock_invoke.assert_called_once()
        # One row for the actor (the legacy bucket here) and the assistant's
        # global row. AI search's global row is not created by a chat turn.
        used = dict(PublicAssistantTokenBudget.objects.values_list("pk", "tokens_used"))
        self.assertEqual(
            used,
            {
                self.legacy_key: MOCK_RESULT["usage"]["totalTokens"],
                budget.GLOBAL_BUDGET_KEYS[budget.FEATURE_ASSISTANT]: MOCK_RESULT["usage"]["totalTokens"],
            },
        )


class InvocationErrorTests(PublicAssistantChatTestBase):
    def test_model_error_returns_502(self):
        with patch(INVOKE_PATH, side_effect=RuntimeError("boom")):
            response = self.client.post(self.chat_url, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "assistant_error")
        self.assertEqual(budget.tokens_used(self.legacy_key), 0)
        self.assertEqual(budget.global_tokens_used(budget.FEATURE_ASSISTANT), 0)


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

    def test_config_issues_a_signed_visitor_identity(self):
        response = self.client.get(self.config_url)

        actor = actors.visitor_actor(response.data["visitor_token"])
        self.assertEqual(actor.kind, actors.KIND_VISITOR)
        self.assertIsNone(actor.replacement)

    def test_every_config_response_is_a_different_visitor_and_is_never_cached(self):
        first = self.client.get(self.config_url)
        second = self.client.get(self.config_url)

        self.assertNotEqual(first.data["visitor_token"], second.data["visitor_token"])
        self.assertNotEqual(
            actors.visitor_actor(first.data["visitor_token"]).key,
            actors.visitor_actor(second.data["visitor_token"]).key,
        )
        # A shared cache replaying this body would hand many people one identity.
        self.assertEqual(first["Cache-Control"], "no-store")

    def test_config_issues_no_identity_and_no_budget_rows_when_disabled(self):
        self.config.public_assistant_enabled = False
        self.config.save()

        response = self.client.get(self.config_url)

        self.assertNotIn("visitor_token", response.data)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())


SESSION = "44444444-4444-4444-4444-444444444444"


class AuditLoggingTests(PublicAssistantChatTestBase):
    def _post(self, **extra):
        payload = {"message": "What is I2G?"}
        payload.update(extra)
        return self.client.post(self.chat_url, payload, format="json")

    def test_success_logs_ok_row(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_OK)
        self.assertEqual(message.reply, MOCK_RESULT["text"])
        self.assertEqual(message.token_usage["totalTokens"], 160)
        self.assertEqual(message.conversation.source, AssistantConversationLog.SOURCE_PUBLIC_CHAT)
        self.assertEqual(message.conversation.total_tokens, 160)

    def test_unavailable_aws_logs_unavailable_row(self):
        self.aws.access_key_id = ""
        self.aws.secret_access_key = ""
        self.aws.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self._post()
        self.assertEqual(response.status_code, 200)
        mock_invoke.assert_not_called()
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_UNAVAILABLE)

    def test_budget_logs_budget_row(self):
        # The assistant's global budget is spent (these requests carry no
        # visitor value, and the legacy actor has no per-actor token limit).
        self.config.public_assistant_global_token_limit = 100
        self.config.save()
        budget.record_usage(budget.GLOBAL_BUDGET_KEYS[budget.FEATURE_ASSISTANT], 100, 86400)
        with (
            patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke,
            self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 429)
        mock_invoke.assert_not_called()
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_BUDGET)

    def test_error_logs_error_row(self):
        with patch(INVOKE_PATH, side_effect=RuntimeError("boom")):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_ERROR)

    def test_session_id_groups_turns(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            self._post(session_id=SESSION)
            self._post(session_id=SESSION)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)
        convo = AssistantConversationLog.objects.get()
        self.assertEqual(convo.message_count, 2)
        self.assertEqual(str(convo.session_id), SESSION)

    def test_garbage_session_id_does_not_400(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self._post(session_id="not-a-uuid")
        self.assertEqual(response.status_code, 200)
        convo = AssistantConversationLog.objects.get()
        self.assertIsNone(convo.session_id)

    def test_disabled_config_branch_is_not_logged(self):
        # The widget-off branch is intentionally NOT audited (pure noise).
        self.config.public_assistant_enabled = False
        self.config.save()
        with patch(INVOKE_PATH):
            self._post()
        self.assertEqual(AssistantMessageLog.objects.count(), 0)

    def test_recorder_failure_does_not_break_response(self):
        # Force the audit write to blow up deep inside the recorder; the
        # visitor must still get their answer (the recorder swallows it).
        with (
            patch(INVOKE_PATH, return_value=MOCK_RESULT),
            patch(
                "apps.system_intelligence.services.usage_log.recorder.AssistantMessageLog.objects.create",
                side_effect=RuntimeError("audit down"),
            ),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["reply"], MOCK_RESULT["text"])
        self.assertEqual(AssistantMessageLog.objects.count(), 0)
