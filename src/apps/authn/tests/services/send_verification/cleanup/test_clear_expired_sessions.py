from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.authn.services.send_verification import clear_expired_sessions


class ClearExpiredSessionsTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        now = timezone.now()
        self.expired = [f"expired{index:02d}".ljust(32, "x") for index in range(7)]
        self.live = [f"live{index:02d}".ljust(32, "x") for index in range(3)]
        Session.objects.bulk_create(
            [
                Session(session_key=key, session_data="e30", expire_date=now - timedelta(seconds=1))
                for key in self.expired
            ]
            + [Session(session_key=key, session_data="e30", expire_date=now + timedelta(hours=1)) for key in self.live]
        )

    def test_database_sessions_are_deleted_in_batches(self):
        with CaptureQueriesContext(connection) as queries:
            cleared = clear_expired_sessions(batch_size=3)

        self.assertEqual(cleared, 7)
        self.assertEqual(set(Session.objects.values_list("session_key", flat=True)), set(self.live))
        deletes = [query["sql"] for query in queries if query["sql"].startswith("DELETE")]
        self.assertEqual(len(deletes), 3)  # 3 + 3 + 1

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.cached_db")
    def test_cached_db_sessions_use_the_same_batched_delete(self):
        self.assertEqual(clear_expired_sessions(batch_size=100), 7)
        self.assertEqual(Session.objects.count(), 3)

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_other_engines_use_their_own_clear_expired(self):
        from django.contrib.sessions.backends.signed_cookies import SessionStore

        with patch.object(SessionStore, "clear_expired") as clear_expired:
            self.assertIsNone(clear_expired_sessions())

        clear_expired.assert_called_once_with()
        self.assertEqual(Session.objects.count(), 10)

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_an_engine_that_cannot_clear_is_skipped_like_clearsessions(self):
        from django.contrib.sessions.backends.signed_cookies import SessionStore

        with patch.object(SessionStore, "clear_expired", side_effect=NotImplementedError):
            self.assertIsNone(clear_expired_sessions())

    def test_batch_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            clear_expired_sessions(batch_size=0)
