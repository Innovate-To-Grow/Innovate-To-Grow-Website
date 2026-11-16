"""Database budgets under real concurrent transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

from django.db import close_old_connections, transaction
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget

from ..budget.budget_helpers import ASSISTANT, ASSISTANT_GLOBAL_KEY


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseBudgetConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_first_reservations_from_separate_connections_do_not_overspend(self):
        ip_hash = budget.hash_ip("203.0.113.22")
        ready = Barrier(2)

        def reserve(_index):
            close_old_connections()
            try:
                ready.wait(timeout=5)
                return (
                    budget.reserve_budget(
                        ip_hash,
                        estimated_input_tokens=60,
                        maximum_output_tokens=0,
                        limit=100,
                        window_seconds=3600,
                    )
                    is not None
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            accepted = list(executor.map(reserve, range(2)))

        self.assertEqual(sum(accepted), 1)
        self.assertEqual(budget.tokens_used(ip_hash), 60)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 1)

    @skipUnlessDBFeature("has_select_for_update", "has_select_for_update_skip_locked")
    def test_cleanup_skips_a_budget_being_reactivated(self):
        ip_hash = budget.hash_ip("203.0.113.23")
        PublicAssistantTokenBudget.objects.create(
            ip_hash=ip_hash,
            window_id=budget._new_window_id(),
            tokens_used=25,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )
        locked = Event()
        release_lock = Event()

        def reactivate():
            close_old_connections()
            try:
                with transaction.atomic():
                    state = PublicAssistantTokenBudget.objects.select_for_update().get(pk=ip_hash)
                    state.window_id = budget._new_window_id()
                    state.tokens_used = 60
                    state.window_expires_at = timezone.now() + timedelta(hours=1)
                    state.save()
                    locked.set()
                    if not release_lock.wait(timeout=5):
                        raise TimeoutError("test did not release the budget row lock")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(reactivate)
            self.assertTrue(locked.wait(timeout=5))
            try:
                self.assertEqual(budget.purge_expired_public_assistant_budgets(), 0)
            finally:
                release_lock.set()
            future.result(timeout=5)

        state = PublicAssistantTokenBudget.objects.get(pk=ip_hash)
        self.assertEqual(state.tokens_used, 60)
        self.assertGreater(state.window_expires_at, timezone.now())

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_actors_cannot_overspend_the_global_budget(self):
        # 8 different actors race for a global budget that fits exactly 3 of
        # them; every per-actor limit is far away. Only the global row lock can
        # serialise them.
        workers = 8
        ready = Barrier(workers)

        def reserve(index):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return (
                    budget.reserve_budget(
                        budget.hash_ip(f"concurrent-actor-{index}"),
                        estimated_input_tokens=60,
                        maximum_output_tokens=0,
                        limit=1000,
                        window_seconds=3600,
                        global_limit=200,
                        feature=ASSISTANT,
                    )
                    is not None
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            accepted = list(executor.map(reserve, range(workers)))

        self.assertEqual(sum(accepted), 3)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 180)
        # One global + one actor reservation per admitted request, none for the refused.
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 6)
        self.assertEqual(PublicAssistantTokenBudget.objects.exclude(pk=ASSISTANT_GLOBAL_KEY).count(), 3)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_reserve_and_settle_do_not_deadlock_or_leak(self):
        # Reserve and settle both take the global row lock and then the actor
        # row lock. Half the workers share ONE actor row, so both locks are
        # contended at once; an inconsistent order would make PostgreSQL abort
        # one transaction with "deadlock detected" (surfacing here as
        # BudgetBackendUnavailable).
        workers, rounds, actual = 6, 10, 7
        shared_actor = budget.hash_ip("churn-shared")
        ready = Barrier(workers)

        def churn(index):
            close_old_connections()
            try:
                actor = shared_actor if index % 2 else budget.hash_ip(f"churn-{index}")
                ready.wait(timeout=10)
                for round_number in range(rounds):
                    reservation = budget.reserve_budget(
                        actor,
                        estimated_input_tokens=10,
                        maximum_output_tokens=0,
                        limit=0,
                        window_seconds=3600,
                        global_limit=1_000_000,
                        feature=ASSISTANT,
                    )
                    if round_number % 2:
                        budget.release_budget(reservation)
                    else:
                        budget.reconcile_budget(reservation, actual)
                return True
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(churn, index) for index in range(workers)]
            completed = [future.result(timeout=60) for future in futures]

        self.assertEqual(completed, [True] * workers)
        reconciled_rounds = (rounds + 1) // 2
        self.assertEqual(budget.global_tokens_used(ASSISTANT), workers * reconciled_rounds * actual)
        self.assertEqual(budget.tokens_used(shared_actor), (workers // 2) * reconciled_rounds * actual)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())
