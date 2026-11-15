from unittest.mock import patch

from apps.system_intelligence.models import (
    AssistantMessageLog,
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.actors.test_actor_limits_api import (
    ACTUAL_TOKENS,
    AI_SEARCH,
    ASSISTANT,
    BUDGET_LOGGER,
    BUDGET_MESSAGE,
    DAY,
    MOCK_RESULT,
    ActorLimitsTestBase,
)


class GlobalBudgetTests(ActorLimitsTestBase):
    def test_global_budget_stops_everyone_with_the_budget_message(self):
        # Fits exactly two turns for the whole site; per-actor limits are far away.
        self.configure(public_assistant_global_token_limit=self.reserved + ACTUAL_TOKENS)
        first, second, third = self.new_visitor(), self.new_visitor(), self.new_visitor()
        self.assertEqual([self.ask(first).status_code, self.ask(second).status_code], [200, 200])

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            refused = [self.ask(third), self.ask(first), self.ask()]

        for response in refused:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "budget_exceeded")
            self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        self.assertEqual(self.invoke.call_count, 2)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 2 * ACTUAL_TOKENS)
        # A refusal charges nobody: no row for the third visitor or the legacy bucket.
        self.assertEqual(self.actor_rows().count(), 2)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(
            AssistantMessageLog.objects.filter(status=AssistantMessageLog.STATUS_BUDGET).count(),
            3,
        )

    def test_reservation_is_held_on_both_budgets_during_the_model_call(self):
        visitor = self.new_visitor()
        seen = {}

        def invoke(**_kwargs):
            seen["actor"] = self.used(visitor)
            seen["global"] = budget.global_tokens_used(ASSISTANT)
            seen["reservations"] = PublicAssistantTokenReservation.objects.count()
            return MOCK_RESULT

        self.invoke.side_effect = invoke

        self.assertEqual(self.ask(visitor).status_code, 200)

        self.assertEqual(seen, {"actor": self.reserved, "global": self.reserved, "reservations": 2})

    def test_success_reconciles_both_budgets_to_actual_usage(self):
        visitor = self.new_visitor()

        self.ask(visitor)

        self.assertEqual(self.used(visitor), ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), ACTUAL_TOKENS)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_provider_error_releases_both_budgets(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        visitor = self.new_visitor()
        self.invoke.side_effect = RuntimeError("bedrock down")

        failures = [self.ask(visitor).status_code for _ in range(3)]

        # Nothing leaked: three failed calls in a row still fit a budget of one.
        self.assertEqual(failures, [502, 502, 502])
        self.assertEqual(self.used(visitor), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

        self.invoke.side_effect = None
        self.assertEqual(self.ask(visitor).status_code, 200)

    def test_zero_global_limit_switches_the_model_calls_off(self):
        self.configure(public_assistant_global_token_limit=0)

        responses = [self.ask(self.new_visitor()), self.ask()]

        for response in responses:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "budget_exceeded")
            self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        self.invoke.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_raising_the_global_limit_restores_service_immediately(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        visitor = self.new_visitor()
        self.assertEqual(self.ask(visitor).status_code, 200)
        with self.assertLogs(BUDGET_LOGGER, level="WARNING"):
            self.assertEqual(self.ask(visitor).status_code, 429)

        self.configure(public_assistant_global_token_limit=10 * self.reserved)

        self.assertEqual(self.ask(visitor).status_code, 200)

    def test_chat_is_charged_to_the_assistants_global_row_only(self):
        self.ask(self.new_visitor())

        self.assertEqual(budget.global_tokens_used(ASSISTANT), ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 0)
        self.assertFalse(
            PublicAssistantTokenBudget.objects.filter(pk=budget.GLOBAL_BUDGET_KEYS[AI_SEARCH]).exists(),
        )

    def test_spent_ai_search_budget_does_not_pause_the_assistant(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        budget.record_usage(budget.GLOBAL_BUDGET_KEYS[AI_SEARCH], self.reserved, DAY)

        with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(budget.global_tokens_used(ASSISTANT), ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), self.reserved)

    def test_default_global_limit_is_two_million_tokens(self):
        self.assertEqual(SystemIntelligenceConfig().public_assistant_global_token_limit, 2_000_000)
        self.assertEqual(self.config.public_assistant_global_token_limit, 2_000_000)

    def test_budget_backend_failure_is_a_503_never_a_500(self):
        with patch.object(budget.database_store, "_locked_database_budget", side_effect=RuntimeError("db down")):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        self.invoke.assert_not_called()
