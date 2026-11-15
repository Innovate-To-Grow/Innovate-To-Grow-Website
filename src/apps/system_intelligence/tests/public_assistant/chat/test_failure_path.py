from unittest.mock import patch

from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
)
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.services.public_assistant.chat import actors
from apps.system_intelligence.tests.public_assistant.actors.test_actor_limits_api import (
    ASSISTANT,
    BUDGET_LOGGER,
    CONTEXT_PATH,
    MOCK_RESULT,
    ActorLimitsTestBase,
)


class FailurePathTests(ActorLimitsTestBase):
    """Infrastructure hiccups around the budget never become a 500 or a leak."""

    def test_context_failure_is_a_503_and_reserves_nothing(self):
        with patch(CONTEXT_PATH, side_effect=RuntimeError("cache down")):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        self.invoke.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_reconcile_failure_does_not_break_the_answer(self):
        with patch(
            "apps.system_intelligence.views.chat_turn.reconcile_budget",
            side_effect=budget.BudgetBackendUnavailable("db blip"),
        ):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reply"], MOCK_RESULT["text"])

    def test_unparsable_provider_usage_is_answered_and_settled_at_the_reservation(self):
        # Not a number: no 500, and neither reservation is left dangling.
        visitor = self.new_visitor()
        self.invoke.return_value = {"text": "An answer.", "usage": {"totalTokens": "n/a"}}

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            response = self.ask(visitor)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["reply"], "An answer.")
        self.assertIn("Unparsable provider token usage", logs.output[0])
        self.assertEqual(self.used(visitor), self.reserved)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), self.reserved)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_release_failure_after_a_provider_error_still_answers_502(self):
        self.invoke.side_effect = RuntimeError("bedrock down")
        with patch(
            "apps.system_intelligence.views.chat_turn.release_budget",
            side_effect=budget.BudgetBackendUnavailable("db blip"),
        ):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "assistant_error")

    def test_input_too_large_is_rejected_before_any_reservation(self):
        self.configure(public_assistant_max_estimated_input_tokens=5)

        response = self.ask()

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["code"], "input_too_large")
        self.assertEqual(actors.visitor_actor(response.data["visitor_token"]).kind, actors.KIND_VISITOR)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
