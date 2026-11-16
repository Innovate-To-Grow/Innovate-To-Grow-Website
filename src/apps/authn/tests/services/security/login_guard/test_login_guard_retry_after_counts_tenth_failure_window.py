from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.authn.services.security import login_guard
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_SHORT_WINDOW

from .login_guard_helpers import EMAIL, LOGGER, GuardTestCase


class LoginGuardTests(GuardTestCase):
    def test_the_tenth_failure_of_a_window_is_logged_with_a_hash_only(self):
        self.record(9)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(1)

        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertIn("window=15m", message)
        self.assertRegex(message, r"identifier_hash=[0-9a-f]{12}$")
        self.assertNotIn("victim", message)

    def test_the_lock_check_is_one_select(self):
        self.record(10)

        with CaptureQueriesContext(connection) as queries:
            self.assertGreater(login_guard.retry_after(EMAIL), 0)

        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]["sql"].startswith("SELECT"))

    def test_the_counters_do_not_live_in_the_cache(self):
        """Production has no Redis: a per-task file cache must not hold (or lose) the lockout."""
        self.record(10)

        cache.clear()

        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW)
