from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.db.models import QuerySet
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.budget_storage.test_budget_database import (
    _DatabaseTwoLevelBudgetCase,
)

from ..budget.budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY, BUDGET_LOGGER


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseTwoLevelBudgetTests(_DatabaseTwoLevelBudgetCase):
    def test_global_usage_read_out_ignores_an_expired_window(self):
        self._reserve(self.actor, amount=150, feature=ASSISTANT)
        self._reserve(self.actor, amount=70, feature=AI_SEARCH)
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).update(
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )

        chat, search = budget.global_budget_usage()

        self.assertEqual((chat.tokens_used, chat.window_expires_at), (0, None))
        self.assertEqual(search.tokens_used, 70)

    def test_global_usage_read_out_is_one_query_and_locks_nothing(self):
        self._reserve(self.actor, amount=150, feature=ASSISTANT)

        # SQLite never emits FOR UPDATE, so also refuse the ORM call itself.
        with (
            patch.object(QuerySet, "select_for_update", side_effect=AssertionError("the read-out must not lock")),
            CaptureQueriesContext(connection) as captured,
        ):
            budget.global_budget_usage()

        self.assertEqual(len(captured), 1)
        self.assertNotIn("FOR UPDATE", captured[0]["sql"].upper())
        # Reading creates nothing.
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=AI_SEARCH_GLOBAL_KEY).exists())

    def test_unparsable_provider_usage_settles_the_reservation_at_the_reserved_amount(self):
        for value in ("x", "12 tokens", float("nan"), float("inf"), object(), [80], {"totalTokens": 80}):
            with self.subTest(value=repr(value)):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
                    budget.reconcile_budget(reservation, value)

                # Charged as reserved on both levels, and the reservation is consumed.
                self.assertEqual(budget.tokens_used(self.actor), 150)
                self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())
                self.assertEqual(len(logs.output), 1)
                self.assertIn("Unparsable provider token usage", logs.output[0])
                self.assertIn("charging the reserved 150 tokens", logs.output[0])

    def test_an_absurdly_large_reported_total_is_treated_as_unreadable(self):
        """A number no call can cost would overflow the counters; the call is settled at the reserved amount."""
        for value in (budget.MAX_REPORTED_TOKENS + 1, 10**30, True):
            with self.subTest(value=value):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                with self.assertLogs(BUDGET_LOGGER, level="WARNING"):
                    budget.reconcile_budget(reservation, value)

                self.assertEqual(budget.tokens_used(self.actor), 150)
                self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_the_largest_plausible_total_and_zero_are_charged_as_reported(self):
        for value, expected in ((0, 0), (None, 0), (-5, 0), ("80", 80), (80.9, 80)):
            with self.subTest(value=value):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                budget.reconcile_budget(reservation, value)

                self.assertEqual(budget.tokens_used(self.actor), expected)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_sanitized_usage_keeps_only_plausible_token_counts(self):
        self.assertEqual(
            budget.sanitized_usage({"inputTokens": 5, "outputTokens": "7", "totalTokens": 12.0, "extra": "x"}),
            {"inputTokens": 5, "outputTokens": 7, "totalTokens": 12},
        )
        self.assertEqual(
            budget.sanitized_usage({"inputTokens": float("nan"), "outputTokens": float("inf"), "totalTokens": 10**30}),
            {},
        )
        self.assertEqual(budget.sanitized_usage({"inputTokens": -1, "outputTokens": True, "totalTokens": None}), {})
        for not_a_mapping in (None, "x", [1], 5):
            self.assertEqual(budget.sanitized_usage(not_a_mapping), {})

    def test_reported_total_tokens_passes_an_unreadable_block_through_to_reconciliation(self):
        self.assertEqual(budget.reported_total_tokens({"totalTokens": 42}), 42)
        self.assertEqual(budget.reported_total_tokens({}), 0)
        self.assertEqual(budget.reported_total_tokens(None), 0)
        # Not a mapping: reconciliation must see it and charge the reserved amount, not zero.
        self.assertEqual(budget.reported_total_tokens(["x"]), ["x"])
        self.assertEqual(budget.reported_total_tokens("garbage"), "garbage")

    def test_unparsable_provider_usage_is_not_echoed_at_length_into_the_log(self):
        reservation = self._reserve(amount=150)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            budget.reconcile_budget(reservation, "z" * 100_000)

        self.assertLess(len(logs.output[0]), 400)

    def test_number_like_provider_usage_is_reconciled_as_a_number(self):
        for value, expected in (("80", 80), (80.9, 80), (None, 0), (0, 0), (-500, 0), ("", 0)):
            with self.subTest(value=value):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
                    budget.reconcile_budget(reservation, value)

                self.assertEqual(budget.tokens_used(self.actor), expected)
                self.assertEqual(budget.global_tokens_used(ASSISTANT), expected)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())
