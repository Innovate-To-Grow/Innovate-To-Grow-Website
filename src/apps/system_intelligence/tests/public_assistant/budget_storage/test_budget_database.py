"""Two-level (actor + feature-global) database budgets: lock ordering and reconciliation."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget

from ..budget.budget_helpers import ASSISTANT, ASSISTANT_GLOBAL_KEY


class _DatabaseTwoLevelBudgetCase(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = budget.hash_ip("actor-a")
        self.other = budget.hash_ip("actor-b")

    def _reserve(
        self,
        actor=None,
        *,
        amount=150,
        limit=0,
        global_limit=5000,
        window_seconds=3600,
        feature=ASSISTANT,
    ):
        return budget.reserve_budget(
            actor or self.actor,
            estimated_input_tokens=amount,
            maximum_output_tokens=0,
            limit=limit,
            window_seconds=window_seconds,
            global_limit=global_limit,
            feature=feature,
        )


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseTwoLevelBudgetTests(_DatabaseTwoLevelBudgetCase):
    """Actor budget + global budget on the authoritative database path."""

    def test_reservation_charges_the_actor_row_and_the_global_row(self):
        reservation = self._reserve()

        self.assertTrue(reservation.database)
        self.assertEqual(reservation.actor_key, self.actor)
        self.assertEqual(reservation.global_reservation.actor_key, ASSISTANT_GLOBAL_KEY)
        self.assertEqual(budget.tokens_used(self.actor), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 2)
        self.assertEqual(
            set(PublicAssistantTokenBudget.objects.values_list("pk", flat=True)),
            {self.actor, ASSISTANT_GLOBAL_KEY},
        )

    def test_global_budget_is_the_sum_over_all_actors(self):
        self._reserve(self.actor, amount=150)
        self._reserve(self.other, amount=70)

        self.assertEqual(budget.tokens_used(self.actor), 150)
        self.assertEqual(budget.tokens_used(self.other), 70)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 220)

    def test_reconcile_settles_both_levels_to_actual_usage(self):
        reservation = self._reserve()

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_release_returns_both_levels_in_full(self):
        self._reserve(self.other, amount=40)
        reservation = self._reserve()

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.actor), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 2)

    def test_two_level_settlement_is_idempotent(self):
        reservation = self._reserve()

        budget.reconcile_budget(reservation, 80)
        budget.reconcile_budget(reservation, 0)
        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)

    def test_actor_over_its_limit_is_refused_and_the_global_row_is_not_charged(self):
        self._reserve(self.other, amount=40)
        budget.record_usage(self.actor, 900, 3600)

        self.assertIsNone(self._reserve(amount=150, limit=1000))

        self.assertEqual(budget.tokens_used(self.actor), 900)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 2)

    def test_exhausted_global_budget_refuses_every_actor_and_charges_nobody(self):
        self._reserve(self.other, amount=4900)

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs:
            refused = self._reserve(amount=150)

        self.assertIsNone(refused)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 4900)
        self.assertEqual(budget.tokens_used(self.actor), 0)
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=self.actor).exists())
        self.assertIn("global token budget exhausted", logs.output[0])

    def test_global_refusal_is_logged_at_most_once_a_minute(self):
        self._reserve(self.other, amount=4900)
        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs:
            for _ in range(5):
                self.assertIsNone(self._reserve(amount=150))

        self.assertEqual(len(logs.output), 1)

    def test_global_budget_admits_exactly_up_to_its_limit(self):
        self.assertIsNotNone(self._reserve(self.actor, amount=3000, limit=0))
        self.assertIsNotNone(self._reserve(self.other, amount=2000, limit=0))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(budget.hash_ip("actor-c"), amount=1, limit=0))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)

    def test_request_larger_than_the_global_limit_creates_no_rows(self):
        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(amount=5001, limit=0))

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_zero_global_limit_refuses_everything_and_creates_no_rows(self):
        # "Switched off" is a setting, not an incident: no exhaustion alarm.
        with self.assertNoLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(amount=1, limit=0, global_limit=0))

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_without_a_global_limit_only_the_actor_row_is_charged(self):
        reservation = self._reserve(global_limit=None)

        self.assertIsNone(reservation.global_reservation)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
        self.assertEqual(budget.tokens_used(self.actor), 150)

    def test_raising_the_global_limit_takes_effect_immediately(self):
        self._reserve(self.other, amount=4900)
        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(amount=150, global_limit=5000))

        self.assertIsNotNone(self._reserve(amount=150, global_limit=6000))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5050)
