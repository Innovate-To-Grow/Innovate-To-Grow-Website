from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
)
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.services.public_assistant.chat import actors
from apps.system_intelligence.tests.public_assistant.chat.test_chat_api import (
    INVOKE_PATH,
    MOCK_RESULT,
    PublicAssistantChatTestBase,
)


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
        "apps.system_intelligence.services.public_assistant.budget.cache_store._shared_redis_client",
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
