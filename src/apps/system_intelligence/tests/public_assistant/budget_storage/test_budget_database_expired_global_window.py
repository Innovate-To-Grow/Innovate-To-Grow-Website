from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.budget_storage.test_budget_database import (
    _DatabaseTwoLevelBudgetCase,
)

from ..budget.budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY
from ..budget.budget_lock_helpers import _budget_row_lock_order


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseTwoLevelBudgetTests(_DatabaseTwoLevelBudgetCase):
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
            patch.object(budget.limits.cache, "add", side_effect=RuntimeError("cache down")),
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

        with patch.object(budget.reservations, "_settle_database_reservation", side_effect=RuntimeError("db down")):
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
