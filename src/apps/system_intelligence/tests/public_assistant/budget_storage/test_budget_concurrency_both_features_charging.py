from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature

from apps.system_intelligence.models import PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget

from ..budget.budget_helpers import AI_SEARCH, ASSISTANT


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseBudgetConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_both_features_charging_one_member_do_not_deadlock_or_leak(self):
        # A member chatting and searching at once: the two features lock
        # DIFFERENT global rows and then the SAME actor row. Nobody who holds
        # the actor row waits for another budget row, so PostgreSQL must never
        # report "deadlock detected" (it would surface here as
        # BudgetBackendUnavailable), and every charge must be settled.
        workers, rounds, actual = 6, 10, 7
        shared_actor = budget.hash_ip("both-features-member")
        ready = Barrier(workers)

        def churn(index):
            close_old_connections()
            try:
                feature = ASSISTANT if index % 2 else AI_SEARCH
                ready.wait(timeout=10)
                for round_number in range(rounds):
                    reservation = budget.reserve_budget(
                        shared_actor,
                        estimated_input_tokens=10,
                        maximum_output_tokens=0,
                        limit=0,
                        window_seconds=3600,
                        global_limit=1_000_000,
                        feature=feature,
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
        per_feature = (workers // 2) * reconciled_rounds * actual
        self.assertEqual(budget.global_tokens_used(ASSISTANT), per_feature)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), per_feature)
        self.assertEqual(budget.tokens_used(shared_actor), 2 * per_feature)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    @skipUnlessDBFeature("has_select_for_update")
    def test_a_concurrent_drain_of_the_assistant_never_refuses_ai_search(self):
        # 8 anonymous actors race for an assistant budget that fits exactly 3
        # of them while 2 members search. The limit is the same number for
        # both features, but each has its own row: both searches are admitted.
        chat_workers, search_workers = 8, 2
        ready = Barrier(chat_workers + search_workers)

        def reserve(index):
            close_old_connections()
            try:
                feature = ASSISTANT if index < chat_workers else AI_SEARCH
                ready.wait(timeout=10)
                reservation = budget.reserve_budget(
                    budget.hash_ip(f"isolation-actor-{index}"),
                    estimated_input_tokens=60,
                    maximum_output_tokens=0,
                    limit=1000,
                    window_seconds=3600,
                    global_limit=200,
                    feature=feature,
                )
                return feature, reservation is not None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=chat_workers + search_workers) as executor:
            outcomes = list(executor.map(reserve, range(chat_workers + search_workers)))

        self.assertEqual(sum(admitted for feature, admitted in outcomes if feature == ASSISTANT), 3)
        self.assertEqual(sum(admitted for feature, admitted in outcomes if feature == AI_SEARCH), 2)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 180)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 120)
