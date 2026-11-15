from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.authn.services import login_guard
from apps.authn.tests.services.security.scoped_key.test_scoped_key import _ScopedKeyCase

from ..login_guard.login_guard_helpers import GLOBAL, LOGGER, SUBJECT


class ScopedKeyTests(_ScopedKeyCase):
    def test_the_lock_is_logged_with_a_hash_only(self):
        self.record(9, self.key)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(1, self.key)

        (record,) = logs.records
        self.assertEqual(
            record.getMessage(), f"Password sign-in locked: window=15m identifier_hash={self.key.digest()[:12]}"
        )
        self.assertNotIn(SUBJECT[:8], record.getMessage())

    def test_the_digest_depends_on_the_secret_key(self):
        with override_settings(SECRET_KEY="first-secret-for-the-digest"):
            first = self.key.digest()
        with override_settings(SECRET_KEY="second-secret-for-the-digest"):
            second = self.key.digest()

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, GLOBAL)

    def test_the_lock_check_is_one_select(self):
        self.record(10, self.key)

        with CaptureQueriesContext(connection) as queries:
            self.assertGreater(login_guard.retry_after(self.key), 0)

        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]["sql"].startswith("SELECT"))
