from django.core.cache import cache
from django.test import override_settings

from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.budget.test_budget_counter import _BudgetCounterCase

from .budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY, BUDGET_LOGGER


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
class BudgetCounterTests(_BudgetCounterCase):
    def test_each_feature_charges_its_own_global_counter(self):
        chat = self._reserve_for(ASSISTANT, amount=150)
        search = self._reserve_for(AI_SEARCH, amount=70)

        self.assertEqual(chat.global_reservation.actor_key, ASSISTANT_GLOBAL_KEY)
        self.assertEqual(search.global_reservation.actor_key, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 70)
        self.assertEqual(budget.tokens_used(self.ip_hash), 220)

        budget.release_budget(chat)
        budget.reconcile_budget(search, 30)

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 30)
        self.assertEqual(budget.tokens_used(self.ip_hash), 30)

    def test_an_exhausted_feature_does_not_refuse_the_other_one(self):
        budget.record_usage(ASSISTANT_GLOBAL_KEY, 5000, 86400)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            refused = self._reserve_for(ASSISTANT)
        admitted = self._reserve_for(AI_SEARCH)

        self.assertIsNone(refused)
        self.assertIsNotNone(admitted)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 150)

    def test_a_global_limit_needs_a_known_feature(self):
        for feature in (None, "", "chat", ["assistant"]):
            for global_limit in (5000, 0):
                with self.subTest(feature=feature, global_limit=global_limit), self.assertRaises(ValueError):
                    budget.reserve_budget(
                        self.ip_hash,
                        estimated_input_tokens=10,
                        maximum_output_tokens=0,
                        limit=0,
                        window_seconds=86400,
                        global_limit=global_limit,
                        feature=feature,
                    )
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)
        for feature in (ASSISTANT, AI_SEARCH):
            self.assertEqual(budget.global_tokens_used(feature), 0)

    def test_unparsable_provider_usage_settles_the_cache_reservation_at_the_reserved_amount(self):
        reservation = self._reserve_for(ASSISTANT, amount=150)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            budget.reconcile_budget(reservation, "not-a-number")

        self.assertIn("Unparsable provider token usage", logs.output[0])
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        # The reservation was consumed: settling it again changes nothing.
        self.assertIsNone(cache.get(reservation.reservation_cache_key))
        budget.release_budget(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)

    def test_global_usage_read_out_on_the_cache_path(self):
        self._reserve_for(AI_SEARCH, amount=70)

        usage = budget.global_budget_usage()

        self.assertEqual(
            [(entry.feature, entry.label, entry.tokens_used, entry.window_expires_at) for entry in usage],
            [(ASSISTANT, "Public assistant", 0, None), (AI_SEARCH, "AI search", 70, None)],
        )
