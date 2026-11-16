import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.budget_storage.test_budget_database import (
    _DatabaseTwoLevelBudgetCase,
)

from ..budget.budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY, BUDGET_LOGGER


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseTwoLevelBudgetTests(_DatabaseTwoLevelBudgetCase):
    def test_purge_removes_an_expired_global_row_and_the_next_request_recreates_it(self):
        reservation = self._reserve()
        PublicAssistantTokenBudget.objects.update(window_expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(budget.purge_expired_public_assistant_budgets(), 2)
        # A settlement arriving after the purge finds nothing to adjust.
        budget.reconcile_budget(reservation, 80)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

        self.assertIsNotNone(self._reserve(amount=40))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)

    def test_database_failure_is_reported_as_backend_unavailable(self):
        with patch.object(budget.database_store, "_locked_database_budget", side_effect=RuntimeError("db down")):
            with self.assertRaises(budget.BudgetBackendUnavailable):
                self._reserve()

        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_global_keys_are_fixed_and_distinct(self):
        # The keys are primary keys of live rows: changing one silently starts
        # that feature on a fresh, empty budget.
        self.assertEqual(
            ASSISTANT_GLOBAL_KEY,
            hashlib.sha256(b"public-assistant:global-budget:assistant").hexdigest(),
        )
        self.assertEqual(
            AI_SEARCH_GLOBAL_KEY,
            hashlib.sha256(b"public-assistant:global-budget:ai-search").hexdigest(),
        )
        self.assertNotEqual(ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(set(budget.GLOBAL_BUDGET_KEYS), {ASSISTANT, AI_SEARCH})
        self.assertEqual(budget.global_budget_key(AI_SEARCH), AI_SEARCH_GLOBAL_KEY)

    def test_each_feature_is_charged_to_its_own_global_row(self):
        chat = self._reserve(self.actor, amount=150, feature=ASSISTANT)
        search = self._reserve(self.other, amount=70, feature=AI_SEARCH)

        self.assertEqual(chat.global_reservation.actor_key, ASSISTANT_GLOBAL_KEY)
        self.assertEqual(search.global_reservation.actor_key, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 70)
        self.assertEqual(
            set(PublicAssistantTokenBudget.objects.values_list("pk", flat=True)),
            {self.actor, self.other, ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY},
        )
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 4)

    def test_a_feature_never_creates_the_other_features_global_row(self):
        self._reserve(feature=AI_SEARCH)

        self.assertEqual(
            set(PublicAssistantTokenBudget.objects.values_list("pk", flat=True)),
            {self.actor, AI_SEARCH_GLOBAL_KEY},
        )

    def test_draining_the_assistant_budget_does_not_pause_ai_search(self):
        # An anonymous script: every request under a freshly minted identity,
        # so no per-actor limit ever binds and only the global row stops it.
        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            admitted = [
                self._reserve(budget.hash_ip(f"minted-{index}"), amount=100, limit=150, feature=ASSISTANT)
                for index in range(60)
            ]

        self.assertEqual(sum(reservation is not None for reservation in admitted), 50)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])

        # A member's AI search has the same limit but its own counter.
        with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
            search = self._reserve(self.other, amount=4000, feature=AI_SEARCH)

        self.assertIsNotNone(search)
        self.assertEqual(search.global_reservation.actor_key, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 4000)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)

    def test_draining_ai_search_does_not_pause_the_assistant(self):
        self.assertIsNotNone(self._reserve(self.other, amount=5000, feature=AI_SEARCH))
        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            self.assertIsNone(self._reserve(self.other, amount=1, feature=AI_SEARCH))

        self.assertIn("global token budget exhausted for AI search", logs.output[0])
        self.assertIsNotNone(self._reserve(self.actor, amount=5000, feature=ASSISTANT))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 5000)

    def test_one_actor_using_both_features_has_one_row_and_two_global_charges(self):
        chat = self._reserve(self.actor, amount=150, limit=1000, feature=ASSISTANT)
        search = self._reserve(self.actor, amount=70, limit=1000, feature=AI_SEARCH)

        # The per-actor limit still spans both features.
        self.assertEqual(budget.tokens_used(self.actor), 220)
        self.assertIsNone(self._reserve(self.actor, amount=781, limit=1000, feature=AI_SEARCH))

        budget.reconcile_budget(chat, 80)
        budget.release_budget(search)

        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_each_feature_logs_its_own_exhaustion_once_a_minute(self):
        self._reserve(self.other, amount=4900, feature=ASSISTANT)
        self._reserve(self.other, amount=4900, feature=AI_SEARCH)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            for _ in range(3):
                self.assertIsNone(self._reserve(amount=150, feature=ASSISTANT))
                self.assertIsNone(self._reserve(amount=150, feature=AI_SEARCH))

        self.assertEqual(len(logs.output), 2)
        self.assertIn("global token budget exhausted for Public assistant (limit 5000 per 86400s)", logs.output[0])
        self.assertIn("global token budget exhausted for AI search (limit 5000 per 86400s)", logs.output[1])

    def test_zero_global_limit_switches_off_either_feature_without_rows(self):
        for feature in (ASSISTANT, AI_SEARCH):
            with self.subTest(feature=feature), self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
                self.assertIsNone(self._reserve(amount=1, limit=0, global_limit=0, feature=feature))

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_a_global_limit_needs_a_known_feature(self):
        for feature in (None, "", "chat", ["assistant"]):
            for global_limit in (5000, 0):
                with self.subTest(feature=feature, global_limit=global_limit), self.assertRaises(ValueError):
                    self._reserve(feature=feature, global_limit=global_limit)
        with self.assertRaises(ValueError):
            budget.global_tokens_used("chat")

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        # Without global accounting there is nothing to name.
        self.assertIsNotNone(self._reserve(global_limit=None, feature=None))

    def test_global_usage_read_out_reports_both_features(self):
        self.assertEqual(
            [
                (entry.feature, entry.label, entry.tokens_used, entry.window_expires_at)
                for entry in budget.global_budget_usage()
            ],
            [(ASSISTANT, "Public assistant", 0, None), (AI_SEARCH, "AI search", 0, None)],
        )
        before = timezone.now()
        self._reserve(self.actor, amount=150, feature=ASSISTANT)
        budget.reconcile_budget(self._reserve(self.other, amount=70, feature=AI_SEARCH), 30)

        chat, search = budget.global_budget_usage()

        self.assertEqual((chat.feature, chat.tokens_used), (ASSISTANT, 150))
        self.assertEqual((search.feature, search.tokens_used), (AI_SEARCH, 30))
        for entry in (chat, search):
            self.assertGreaterEqual(entry.window_expires_at, before + timedelta(hours=24))
            self.assertLessEqual(entry.window_expires_at, timezone.now() + timedelta(hours=24))
