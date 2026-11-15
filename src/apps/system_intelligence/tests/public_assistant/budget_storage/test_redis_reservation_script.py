from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.system_intelligence.services.public_assistant import budget

from ..budget.budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY


class _RedisReservationScriptCase(TestCase):
    def setUp(self):
        # Redis is mocked here, but the once-a-minute global-exhaustion warning is deduplicated in the Django
        # cache, so a key left by an earlier test that hit that warning would silence the one asserted below.
        cache.clear()


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="redis://configured")
class RedisReservationScriptTests(_RedisReservationScriptCase):
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
