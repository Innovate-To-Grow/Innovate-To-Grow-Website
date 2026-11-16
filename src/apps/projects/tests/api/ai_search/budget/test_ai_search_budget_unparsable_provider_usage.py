from unittest.mock import patch

from django.test import override_settings

from apps.projects.tests.api.ai_search.budget.test_ai_search_budget import _PastProjectAISearchBudgetCase
from apps.system_intelligence.models import (
    AssistantMessageLog,
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
)
from apps.system_intelligence.services.public_assistant import (
    FEATURE_AI_SEARCH,
    BudgetBackendUnavailable,
    budget,
    global_tokens_used,
)

from ..helpers.ai_search_helpers import BUDGET_LOGGER, SERVICE_AGENT, VIEW_SEARCH, agent_result


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class PastProjectAISearchBudgetTests(_PastProjectAISearchBudgetCase):
    def test_unparsable_provider_usage_is_answered_and_settled_at_the_reservation(self):
        outcome = {"project_ids": [str(self.project.id)], "usage": {"totalTokens": "n/a"}}

        with (
            patch(VIEW_SEARCH, return_value=outcome),
            self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs,
        ):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual([row["id"] for row in response.data["results"]], [str(self.project.id)])
        self.assertIn("Unparsable provider token usage", logs.output[0])
        self.assertEqual(budget.tokens_used(self.member_key), self.reserved)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), self.reserved)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_a_usage_block_that_is_not_plain_integers_is_never_echoed_or_a_500(self):
        odd_blocks = (
            {"inputTokens": float("nan"), "outputTokens": float("inf"), "totalTokens": float("nan")},
            {"inputTokens": 5, "outputTokens": 7, "totalTokens": 10**30},
            ["not", "a", "mapping"],
        )
        for usage in odd_blocks:
            with self.subTest(usage=repr(usage)[:60]):
                PublicAssistantTokenBudget.objects.all().delete()
                PublicAssistantTokenReservation.objects.all().delete()
                outcome = {"project_ids": [str(self.project.id)], "usage": usage}

                with patch(VIEW_SEARCH, return_value=outcome), self.assertLogs(BUDGET_LOGGER, level="WARNING"):
                    response = self.search()

                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.data["results"]], [str(self.project.id)])
                for value in response.data["usage"].values():
                    self.assertIs(type(value), int)
                    self.assertLessEqual(value, budget.MAX_REPORTED_TOKENS)
                # Unreadable usage is charged as reserved, never as nothing, and the reservation is consumed.
                self.assertEqual(budget.tokens_used(self.member_key), self.reserved)
                self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), self.reserved)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_zero_global_limit_switches_the_model_call_off(self):
        self.configure(public_assistant_global_token_limit=0)

        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            response = self.search()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        mock_agent.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_provider_error_releases_the_member_and_global_reservations(self):
        self.configure(public_assistant_global_token_limit=self.reserved)

        with patch(SERVICE_AGENT, side_effect=RuntimeError("bedrock down")):
            statuses = [self.search().status_code for _ in range(3)]

        # Nothing leaked: three failures in a row still fit a budget of one search.
        self.assertEqual(statuses, [502, 502, 502])
        self.assertEqual(budget.tokens_used(self.member_key), 0)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

        with patch(VIEW_SEARCH, return_value=self.outcome):
            self.assertEqual(self.search().status_code, 200)

    def test_query_without_candidates_spends_nothing_and_skips_the_model(self):
        self.configure(public_assistant_global_token_limit=0)

        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            response = self.search(query="zzzzzz")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["usage"]["totalTokens"], 0)
        mock_agent.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        self.assertEqual(AssistantMessageLog.objects.get().status, AssistantMessageLog.STATUS_OK)

    def test_budget_backend_failure_is_a_503_never_a_500(self):
        with (
            patch(
                "apps.projects.views.ai_search.reserve_budget",
                side_effect=BudgetBackendUnavailable("db down"),
            ),
            patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent,
        ):
            response = self.search()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        mock_agent.assert_not_called()

    def test_preparation_failure_is_a_502_and_spends_nothing(self):
        with (
            patch(
                "apps.projects.views.ai_search.prepare_past_project_ai_search",
                side_effect=RuntimeError("candidate query failed"),
            ),
            patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent,
        ):
            response = self.search()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ai_search_error")
        mock_agent.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        self.assertEqual(AssistantMessageLog.objects.get().status, AssistantMessageLog.STATUS_ERROR)

    def test_reconcile_failure_does_not_break_the_response(self):
        with (
            patch(VIEW_SEARCH, return_value=self.outcome),
            patch(
                "apps.projects.views.ai_search.reconcile_budget",
                side_effect=BudgetBackendUnavailable("db blip"),
            ),
        ):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_release_failure_still_answers_502(self):
        with (
            patch(VIEW_SEARCH, side_effect=RuntimeError("bedrock down")),
            patch(
                "apps.projects.views.ai_search.release_budget",
                side_effect=BudgetBackendUnavailable("db blip"),
            ),
        ):
            response = self.search()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ai_search_error")
