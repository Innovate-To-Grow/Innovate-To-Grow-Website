from unittest.mock import Mock, patch

from django.test import override_settings

from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.budget_storage.test_redis_reservation_script import (
    _RedisReservationScriptCase,
)

from ..budget.budget_helpers import ASSISTANT


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="redis://configured")
class RedisReservationScriptTests(_RedisReservationScriptCase):
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
