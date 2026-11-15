from unittest.mock import MagicMock, patch

from django.test import override_settings

from apps.projects.tests.api.ai_search.budget.test_ai_search_budget import _PastProjectAISearchBudgetCase
from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
)
from apps.system_intelligence.services.public_assistant import (
    FEATURE_AI_SEARCH,
    FEATURE_ASSISTANT,
    budget,
    global_tokens_used,
    record_usage,
)

from ..helpers.ai_search_helpers import (
    ASSISTANT_GLOBAL_KEY,
    BUDGET_LOGGER,
    BUDGET_MESSAGE,
    OUTCOME_TOKENS,
    SEARCH_GLOBAL_KEY,
    SERVICE_AGENT,
    VIEW_SEARCH,
    agent_result,
)


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class PastProjectAISearchBudgetTests(_PastProjectAISearchBudgetCase):
    def test_search_cannot_overshoot_a_nearly_spent_budget(self):
        # Old behaviour: "used < limit" admitted the search, then its whole cost
        # was recorded on top (49,999 + one search = 64,699).
        limit = self.reserved + 500
        self.configure(public_assistant_ip_token_limit=limit)
        record_usage(self.member_key, limit - 1, 3600)

        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            response = self.search()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        mock_agent.assert_not_called()
        self.assertEqual(budget.tokens_used(self.member_key), limit - 1)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 0)

    def test_budget_is_reserved_before_the_model_call_and_reconciled_after(self):
        seen = {}

        def agent(**_kwargs):
            seen["member"] = budget.tokens_used(self.member_key)
            seen["global"] = global_tokens_used(FEATURE_AI_SEARCH)
            seen["reservations"] = PublicAssistantTokenReservation.objects.count()
            return MagicMock(
                text=f'{{"ids": ["{self.project.id}"]}}',
                usage={"inputTokens": 200, "outputTokens": 20, "totalTokens": 220},
            )

        with patch(SERVICE_AGENT, side_effect=agent) as mock_agent:
            response = self.search()

        self.assertEqual(response.status_code, 200)
        mock_agent.assert_called_once()
        self.assertEqual(seen, {"member": self.reserved, "global": self.reserved, "reservations": 2})
        # The reservation covers the output cap the model was actually given.
        self.assertEqual(mock_agent.call_args.kwargs["max_tokens"], 700)
        self.assertGreater(self.reserved, 700)
        self.assertEqual(budget.tokens_used(self.member_key), 220)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 220)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_member_can_search_until_the_reservation_no_longer_fits(self):
        self.configure(public_assistant_ip_token_limit=self.reserved + OUTCOME_TOKENS)

        with patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search:
            statuses = [self.search().status_code for _ in range(3)]

        self.assertEqual(statuses, [200, 200, 429])
        self.assertEqual(mocked_search.call_count, 2)
        self.assertLessEqual(budget.tokens_used(self.member_key), self.reserved + OUTCOME_TOKENS)

    def test_exhausted_global_budget_blocks_every_member_with_the_budget_message(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        record_usage(SEARCH_GLOBAL_KEY, 1, 86400)

        with (
            patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search,
            self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs,
        ):
            responses = [self.search(self.member), self.search(self.other_member)]

        self.assertIn("global token budget exhausted for AI search", logs.output[0])

        for response in responses:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "budget_exceeded")
            self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        mocked_search.assert_not_called()
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 1)
        self.assertFalse(PublicAssistantTokenBudget.objects.exclude(pk=SEARCH_GLOBAL_KEY).exists())

    def test_draining_the_assistant_with_minted_identities_does_not_pause_member_search(self):
        # The global limit is ONE number, but each feature has its own counter.
        # Room for exactly three chat turns (5 tokens each after reconciling).
        chat_reserved = self._chat_reserved()
        self.assertLess(self.reserved + OUTCOME_TOKENS, chat_reserved)
        self.configure(public_assistant_global_token_limit=chat_reserved + 10, public_assistant_enabled=True)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            statuses, model_calls = self._anonymous_chat(minted_identities=6)

        # Every request was a brand-new visitor, so no per-visitor limit bound:
        # the assistant's global budget is what stopped the script.
        self.assertEqual(statuses, [200, 200, 200, 429, 429, 429])
        self.assertEqual(model_calls, 3)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 15)

        # Members' AI search is untouched by it: same limit, separate counter.
        with (
            patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search,
            self.assertNoLogs(BUDGET_LOGGER, level="WARNING"),
        ):
            responses = [self.search(self.member), self.search(self.other_member)]

        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["available"])
        self.assertEqual(mocked_search.call_count, 2)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 2 * OUTCOME_TOKENS)
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 15)

    def test_spent_search_budget_does_not_pause_the_public_assistant(self):
        chat_reserved = self._chat_reserved()
        self.configure(public_assistant_global_token_limit=chat_reserved, public_assistant_enabled=True)
        record_usage(SEARCH_GLOBAL_KEY, chat_reserved, 86400)

        with (
            patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search,
            self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs,
        ):
            refused = self.search()
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.data["code"], "budget_exceeded")
        mocked_search.assert_not_called()
        self.assertIn("global token budget exhausted for AI search", logs.output[0])

        with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
            statuses, model_calls = self._anonymous_chat(minted_identities=1)

        self.assertEqual((statuses, model_calls), ([200], 1))
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 5)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), chat_reserved)

    def test_a_spent_assistant_budget_row_is_not_what_search_is_checked_against(self):
        # The assistant's row is far over the limit; a search still fits its own.
        self.configure(public_assistant_global_token_limit=self.reserved)
        record_usage(ASSISTANT_GLOBAL_KEY, 10 * self.reserved, 86400)

        with patch(VIEW_SEARCH, return_value=self.outcome):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), OUTCOME_TOKENS)
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 10 * self.reserved)
