"""Budget backends: the database fallback and the Redis reservation script."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget

from .budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY


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


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="redis://configured")
class RedisReservationScriptTests(TestCase):
    def setUp(self):
        # Redis is mocked here, but the once-a-minute global-exhaustion warning is deduplicated in the Django
        # cache, so a key left by an earlier test that hit that warning would silence the one asserted below.
        cache.clear()

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_reservation_uses_remaining_budget_window_ttl(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = 150
        redis_connection.return_value = redis_client

        reservation = budget.reserve_budget(
            budget.hash_ip("203.0.113.9"),
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=60,
        )

        self.assertIsNotNone(reservation)
        reserve_args = redis_client.eval.call_args.args
        self.assertIs(reserve_args[0], budget._RESERVE_SCRIPT)
        self.assertEqual(reserve_args[1], 3)
        self.assertEqual(reserve_args[2], reservation.budget_cache_key)
        self.assertEqual(reserve_args[3], reservation.window_cache_key)
        self.assertEqual(reserve_args[4], reservation.reservation_cache_key)
        self.assertEqual(reserve_args[5:8], (150, 1000, 60_000))
        self.assertIn("budget_ttl = redis.call('PTTL', KEYS[1])", budget._RESERVE_SCRIPT)
        self.assertIn(
            "redis.call('PSETEX', KEYS[3], budget_ttl",
            budget._RESERVE_SCRIPT,
        )

    def test_missing_redis_backend_is_reported_as_backend_unavailable(self):
        # REDIS_URL is configured but no Redis-backed cache is reachable, and the
        # local fallback is off: fail closed instead of silently not budgeting.
        with self.assertRaises(budget.BudgetBackendUnavailable):
            budget._shared_redis_client()

    def test_reconcile_and_release_require_the_original_window(self):
        for script in (budget._RECONCILE_SCRIPT, budget._RELEASE_SCRIPT):
            self.assertIn("active_window_id ~= reservation_window_id", script)
            self.assertIn("redis.call('EXISTS', KEYS[1]) == 0", script)
            guard_position = script.index("active_window_id ~= reservation_window_id")
            mutation_position = script.index("redis.call('INCRBY', KEYS[1]")
            self.assertLess(guard_position, mutation_position)

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_two_level_redis_reservation_charges_global_then_actor(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = 150
        redis_connection.return_value = redis_client
        actor = budget.hash_ip("203.0.113.9")

        reservation = budget.reserve_budget(
            actor,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=60,
            global_limit=5000,
            feature=ASSISTANT,
        )

        global_call, actor_call = (call.args for call in redis_client.eval.call_args_list)
        self.assertEqual(global_call[2], cache.make_key(budget.budget_key(ASSISTANT_GLOBAL_KEY)))
        self.assertEqual(global_call[5:8], (150, 5000, budget.GLOBAL_WINDOW_SECONDS * 1000))
        self.assertEqual(actor_call[2], cache.make_key(budget.budget_key(actor)))
        self.assertEqual(actor_call[5:8], (150, 1000, 60_000))
        self.assertEqual(reservation.global_reservation.budget_cache_key, global_call[2])

        redis_client.eval.reset_mock()
        budget.reconcile_budget(reservation, 80)

        scripts = [call.args[0] for call in redis_client.eval.call_args_list]
        self.assertEqual(scripts, [budget._RECONCILE_SCRIPT, budget._RECONCILE_SCRIPT])
        settled_keys = {call.args[2] for call in redis_client.eval.call_args_list}
        self.assertEqual(settled_keys, {global_call[2], actor_call[2]})

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_redis_reservation_charges_the_global_counter_of_its_feature(self, redis_connection):
        actor = budget.hash_ip("203.0.113.9")
        for feature, global_key in ((ASSISTANT, ASSISTANT_GLOBAL_KEY), (AI_SEARCH, AI_SEARCH_GLOBAL_KEY)):
            with self.subTest(feature=feature):
                redis_client = Mock()
                redis_client.eval.return_value = 150
                redis_connection.return_value = redis_client

                reservation = budget.reserve_budget(
                    actor,
                    estimated_input_tokens=100,
                    maximum_output_tokens=50,
                    limit=1000,
                    window_seconds=60,
                    global_limit=5000,
                    feature=feature,
                )

                global_call = redis_client.eval.call_args_list[0].args
                self.assertEqual(global_call[2], cache.make_key(budget.budget_key(global_key)))
                self.assertEqual(reservation.global_reservation.actor_key, global_key)

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_redis_actor_refusal_or_failure_returns_the_global_charge(self, redis_connection):
        actor = budget.hash_ip("203.0.113.9")
        for label, actor_step, expected in (
            ("refused", -1, None),
            ("backend failure", RuntimeError("redis down"), budget.BudgetBackendUnavailable),
        ):
            with self.subTest(label):
                redis_client = Mock()
                # global reserve OK -> actor reserve refused/fails -> global release
                redis_client.eval.side_effect = [150, actor_step, 1]
                redis_connection.return_value = redis_client

                def reserve():
                    return budget.reserve_budget(
                        actor,
                        estimated_input_tokens=100,
                        maximum_output_tokens=50,
                        limit=1000,
                        window_seconds=60,
                        global_limit=5000,
                        feature=ASSISTANT,
                    )

                if expected is None:
                    self.assertIsNone(reserve())
                else:
                    with self.assertRaises(expected):
                        reserve()

                release_call = redis_client.eval.call_args_list[2].args
                self.assertIs(release_call[0], budget._RELEASE_SCRIPT)
                self.assertEqual(release_call[2], cache.make_key(budget.budget_key(ASSISTANT_GLOBAL_KEY)))

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_redis_settlement_attempts_both_levels_even_if_one_fails(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = 150
        redis_connection.return_value = redis_client
        reservation = budget.reserve_budget(
            budget.hash_ip("203.0.113.9"),
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=60,
            global_limit=5000,
            feature=ASSISTANT,
        )
        redis_client.eval.reset_mock()
        redis_client.eval.side_effect = [RuntimeError("blip"), 1]

        with self.assertRaises(budget.BudgetBackendUnavailable):
            budget.release_budget(reservation)

        self.assertEqual(redis_client.eval.call_count, 2)

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_single_level_redis_failure_is_reported_as_backend_unavailable(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.side_effect = RuntimeError("redis down")
        redis_connection.return_value = redis_client

        with self.assertRaises(budget.BudgetBackendUnavailable):
            budget.reserve_budget(
                budget.hash_ip("203.0.113.9"),
                estimated_input_tokens=100,
                maximum_output_tokens=50,
                limit=1000,
                window_seconds=60,
            )

        self.assertEqual(redis_client.eval.call_count, 1)

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_failing_to_return_the_global_charge_is_logged_not_raised(self, redis_connection):
        redis_client = Mock()
        # global reserve OK -> actor refused -> returning the global charge fails
        redis_client.eval.side_effect = [150, -1, RuntimeError("redis down")]
        redis_connection.return_value = redis_client

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="ERROR") as logs:
            reservation = budget.reserve_budget(
                budget.hash_ip("203.0.113.9"),
                estimated_input_tokens=100,
                maximum_output_tokens=50,
                limit=1000,
                window_seconds=60,
                global_limit=5000,
                feature=ASSISTANT,
            )

        self.assertIsNone(reservation)
        self.assertIn("Could not return an unused global assistant reservation", logs.output[0])

    @patch.object(budget.cache_store, "_shared_redis_client")
    def test_redis_global_refusal_never_touches_the_actor_counter(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = -1
        redis_connection.return_value = redis_client

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            reservation = budget.reserve_budget(
                budget.hash_ip("203.0.113.9"),
                estimated_input_tokens=100,
                maximum_output_tokens=50,
                limit=1000,
                window_seconds=60,
                global_limit=5000,
                feature=ASSISTANT,
            )

        self.assertIsNone(reservation)
        self.assertEqual(redis_client.eval.call_count, 1)
