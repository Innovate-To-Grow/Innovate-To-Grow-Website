"""Budget backends: the database fallback and the Redis reservation script."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseBudgetFallbackTests(TestCase):
    def setUp(self):
        self.ip_hash = budget.hash_ip("203.0.113.20")

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_reservation_reconcile_and_release_use_the_shared_database(self, redis_connection):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=3600,
        )

        self.assertIsNotNone(reservation)
        self.assertTrue(reservation.database)
        self.assertIsNotNone(reservation.database_reservation_id)
        redis_connection.assert_not_called()
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)

        budget.reconcile_budget(reservation, 80)
        self.assertEqual(budget.tokens_used(self.ip_hash), 80)

        second = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=40,
            maximum_output_tokens=10,
            limit=1000,
            window_seconds=3600,
        )
        self.assertEqual(budget.tokens_used(self.ip_hash), 130)
        budget.release_budget(second)
        self.assertEqual(budget.tokens_used(self.ip_hash), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_database_settlement_is_idempotent(self):
        first = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=60,
            maximum_output_tokens=0,
            limit=1000,
            window_seconds=3600,
        )
        second = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=30,
            maximum_output_tokens=0,
            limit=1000,
            window_seconds=3600,
        )

        budget.reconcile_budget(first, 20)
        self.assertEqual(budget.tokens_used(self.ip_hash), 50)

        budget.reconcile_budget(first, 0)
        budget.release_budget(first)
        self.assertEqual(budget.tokens_used(self.ip_hash), 50)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 1)

        budget.release_budget(second)
        self.assertEqual(budget.tokens_used(self.ip_hash), 20)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_impossible_first_reservation_does_not_anchor_a_window(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=101,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=3600,
        )

        self.assertIsNone(reservation)
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=self.ip_hash).exists())
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_database_reservation_enforces_the_limit_atomically(self):
        budget.record_usage(self.ip_hash, 80, 3600)

        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=21,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=3600,
        )

        self.assertIsNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 80)

    def test_late_reconcile_does_not_mutate_a_new_database_window(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=3600,
        )
        state = PublicAssistantTokenBudget.objects.get(pk=self.ip_hash)
        state.window_id = budget._new_window_id()
        state.tokens_used = 40
        state.window_expires_at = timezone.now() + timedelta(hours=1)
        state.save()

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.ip_hash), 40)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_expired_database_counter_starts_a_fresh_window(self):
        PublicAssistantTokenBudget.objects.create(
            ip_hash=self.ip_hash,
            window_id=budget._new_window_id(),
            tokens_used=999,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )

        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=25,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=3600,
        )

        self.assertIsNotNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 25)

    def test_cleanup_deletes_only_expired_budget_rows(self):
        expired_hash = budget.hash_ip("203.0.113.21")
        expired = PublicAssistantTokenBudget.objects.create(
            ip_hash=expired_hash,
            window_id=budget._new_window_id(),
            tokens_used=25,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )
        PublicAssistantTokenReservation.objects.create(
            budget=expired,
            window_id=expired.window_id,
            reserved_tokens=25,
        )
        budget.record_usage(self.ip_hash, 10, 3600)

        self.assertEqual(budget.purge_expired_public_assistant_budgets(), 1)

        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=expired_hash).exists())
        self.assertTrue(PublicAssistantTokenBudget.objects.filter(pk=self.ip_hash).exists())
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())
