"""Two-level (actor + feature-global) database budgets: lock ordering and reconciliation."""

import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget

from .budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY, BUDGET_LOGGER
from .budget_lock_helpers import _budget_row_lock_order


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseTwoLevelBudgetTests(TestCase):
    """Actor budget + global budget on the authoritative database path."""

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

    def test_expired_global_window_starts_fresh_while_actor_windows_continue(self):
        self._reserve(self.actor, amount=150, window_seconds=7 * 86400)
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).update(
            tokens_used=4999,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertIsNotNone(self._reserve(self.actor, amount=100, window_seconds=7 * 86400))

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 100)
        self.assertEqual(budget.tokens_used(self.actor), 250)

    def test_global_window_is_twenty_four_hours(self):
        before = timezone.now()
        self._reserve()

        expires_at = PublicAssistantTokenBudget.objects.get(pk=ASSISTANT_GLOBAL_KEY).window_expires_at
        self.assertEqual(budget.GLOBAL_WINDOW_SECONDS, 86400)
        self.assertGreaterEqual(expires_at, before + timedelta(hours=24))
        self.assertLessEqual(expires_at, timezone.now() + timedelta(hours=24))

    def test_late_settlement_only_touches_the_window_it_was_charged_to(self):
        reservation = self._reserve()
        # The global window rolled over while the model call was in flight.
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).update(
            window_id=budget._new_window_id(),
            tokens_used=40,
        )

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)
        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_global_charge_is_still_settled_when_the_actor_row_was_purged(self):
        reservation = self._reserve()
        PublicAssistantTokenBudget.objects.filter(pk=self.actor).delete()

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_actor_charge_is_still_settled_when_the_global_row_was_purged(self):
        reservation = self._reserve()
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).delete()

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.actor), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_reserve_locks_only_its_own_global_row_and_before_the_actor_row(self):
        # Every budget row a reservation could touch. A feature must lock its
        # OWN global row, then the actor row, and never the other feature's.
        keys = [self.actor, ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY]
        for feature, global_key in ((ASSISTANT, ASSISTANT_GLOBAL_KEY), (AI_SEARCH, AI_SEARCH_GLOBAL_KEY)):
            for label in ("first use", "existing rows"):
                with self.subTest(feature=feature, state=label):
                    with CaptureQueriesContext(connection) as captured:
                        self._reserve(feature=feature)

                    self.assertEqual(
                        _budget_row_lock_order(captured.captured_queries, keys),
                        [global_key, self.actor],
                    )

    def test_settlement_locks_only_its_own_global_row_and_before_the_actor_row(self):
        keys = [self.actor, ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY]
        for feature, global_key in ((ASSISTANT, ASSISTANT_GLOBAL_KEY), (AI_SEARCH, AI_SEARCH_GLOBAL_KEY)):
            # Both features' rows exist, so a settlement that touched the wrong one would show.
            self._reserve(self.other, feature=ASSISTANT)
            self._reserve(self.other, feature=AI_SEARCH)
            for label, settle in (
                ("reconcile", lambda reservation: budget.reconcile_budget(reservation, 80)),
                ("release", budget.release_budget),
            ):
                with self.subTest(feature=feature, settlement=label):
                    reservation = self._reserve(feature=feature)
                    with CaptureQueriesContext(connection) as captured:
                        settle(reservation)

                    self.assertEqual(
                        _budget_row_lock_order(captured.captured_queries, keys),
                        [global_key, self.actor],
                    )

    def test_refusal_stays_a_refusal_when_the_alarm_cache_is_down(self):
        self._reserve(self.other, amount=4900)

        with (
            patch.object(budget.cache, "add", side_effect=RuntimeError("cache down")),
            self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs,
        ):
            refused = self._reserve(amount=150)

        self.assertIsNone(refused)
        self.assertIn("global token budget exhausted", logs.output[0])

    def test_partly_settled_reservation_settles_the_remaining_level(self):
        reservation = self._reserve()
        PublicAssistantTokenReservation.objects.filter(
            pk=reservation.global_reservation.database_reservation_id
        ).delete()

        budget.reconcile_budget(reservation, 80)

        # The actor's charge is settled; the global counter is left alone
        # because its reservation record is gone (never settled twice).
        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_settling_a_reservation_without_database_rows_is_a_no_op(self):
        empty = budget.BudgetReservation(
            budget_cache_key="",
            window_cache_key="",
            reservation_cache_key="",
            reserved_tokens=10,
            window_seconds=3600,
            shared_redis=False,
            database=True,
            actor_key=self.actor,
        )

        budget.reconcile_budget(empty, 5)
        budget.release_budget(empty)

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_settlement_failure_is_reported_as_backend_unavailable(self):
        reservation = self._reserve()

        with patch.object(budget, "_settle_database_reservation", side_effect=RuntimeError("db down")):
            with self.assertRaises(budget.BudgetBackendUnavailable):
                budget.reconcile_budget(reservation, 80)
            with self.assertRaises(budget.BudgetBackendUnavailable):
                budget.release_budget(reservation)

        # Still settleable once the database is back.
        budget.release_budget(reservation)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)

    def test_purge_with_nothing_expired_deletes_nothing(self):
        self._reserve()

        self.assertEqual(budget.purge_expired_public_assistant_budgets(), 0)
        self.assertEqual(PublicAssistantTokenBudget.objects.count(), 2)

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

    # ----- one global row per feature -------------------------------------

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

    # ----- usage read-out (shown in Django admin) --------------------------

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

    # ----- provider usage that is not a number ------------------------------

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
