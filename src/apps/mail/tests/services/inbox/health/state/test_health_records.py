"""``inbox.health``: recording the outcome of every read, and loading the states once per inbox request."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.reading.connection import InboxBusy, InboxError
from apps.mail.tests.services.inbox.health.state.helpers import (
    ACCOUNT,
    GRAPH,
    LOGGER,
    HealthCase,
    Status,
    messages,
    state,
)


class RecordTests(HealthCase):
    def test_a_read_without_messages_records_the_connection_only(self):
        health.record_ok(ACCOUNT, now=self.now)

        row = InboxAccountState.objects.get(account_key=ACCOUNT.key)
        self.assertEqual(
            (row.address, row.status, row.detail, row.checked_at, row.connected_at, row.consecutive_failures),
            (ACCOUNT.address, Status.OK, "", self.now, self.now, 0),
        )
        self.assertIsNone(row.snapshot_at)
        self.assertEqual((row.messages, row.unread_count), ([], 0))

    def test_messages_replace_the_snapshot_capped_and_counted(self):
        health.record_ok(ACCOUNT, messages=messages(60, unread_every=3), now=self.now)

        row = InboxAccountState.objects.get(account_key=ACCOUNT.key)
        self.assertEqual(len(row.messages), health.SNAPSHOT_LIMIT)
        self.assertEqual(row.messages[0]["uid"], "0")
        # Unread among the 50 kept: uids 0, 3, ..., 48.
        self.assertEqual(row.unread_count, 17)
        self.assertEqual(row.snapshot_at, self.now)

    def test_a_connection_after_failures_clears_them_and_keeps_the_snapshot(self):
        state(
            ACCOUNT,
            status=Status.UNREACHABLE,
            detail="Could not connect",
            consecutive_failures=4,
            snapshot_at=self.now - timedelta(hours=1),
            messages=messages(2),
            unread_count=2,
        )

        health.record_ok(ACCOUNT, now=self.now)

        row = InboxAccountState.objects.get(account_key=ACCOUNT.key)
        self.assertEqual((row.status, row.detail, row.consecutive_failures), (Status.OK, "", 0))
        self.assertEqual((len(row.messages), row.unread_count), (2, 2))
        self.assertEqual(row.snapshot_at, self.now - timedelta(hours=1))

    def test_a_held_back_read_is_busy(self):
        state(ACCOUNT, status=Status.OK, messages=messages(2), snapshot_at=self.now, consecutive_failures=1)

        health.record_failure(ACCOUNT, InboxBusy("Gmail is busy; try again in about 30 seconds.", 30), now=self.now)

        row = InboxAccountState.objects.get(account_key=ACCOUNT.key)
        self.assertEqual(
            (row.status, row.detail, row.checked_at, row.consecutive_failures),
            (Status.BUSY, "Gmail is busy; try again in about 30 seconds.", self.now, 2),
        )
        self.assertEqual(len(row.messages), 2)

    def test_a_refused_sign_in_is_unreachable_with_its_busy_text(self):
        health.record_failure(ACCOUNT, InboxBusy("Gmail refused the sign-in.", 600, refused=True), now=self.now)

        row = InboxAccountState.objects.get(account_key=ACCOUNT.key)
        self.assertEqual(
            (row.status, row.detail, row.address), (Status.UNREACHABLE, "Gmail refused the sign-in.", ACCOUNT.address)
        )
        self.assertEqual(row.consecutive_failures, 1)

    def test_any_other_failure_is_unreachable_without_the_raw_error(self):
        for exc in (InboxError("IMAP login failed: password=hunter2"), RuntimeError("socket: secret")):
            with self.subTest(exc=type(exc).__name__):
                health.record_failure(ACCOUNT, exc, now=self.now)

                row = InboxAccountState.objects.get(account_key=ACCOUNT.key)
                self.assertEqual((row.status, row.detail), (Status.UNREACHABLE, health.UNREACHABLE_DETAIL))
        self.assertEqual(InboxAccountState.objects.get(account_key=ACCOUNT.key).consecutive_failures, 2)

    def test_a_long_busy_text_is_cut_to_the_column(self):
        health.record_failure(ACCOUNT, InboxBusy("x" * 400, 30))

        self.assertEqual(len(InboxAccountState.objects.get(account_key=ACCOUNT.key).detail), 255)

    def test_recording_never_raises(self):
        # Every write locks the account's row first (``health._save``).
        with (
            patch.object(InboxAccountState.objects, "select_for_update", side_effect=DatabaseError("locked")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            health.record_ok(ACCOUNT)
        with (
            patch.object(InboxAccountState.objects, "select_for_update", side_effect=DatabaseError("locked")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            health.record_failure(ACCOUNT, RuntimeError("boom"))

        self.assertFalse(InboxAccountState.objects.exists())

    def test_every_record_drops_the_cached_unread_count(self):
        for record in (
            lambda: health.record_ok(ACCOUNT),
            lambda: health.record_failure(ACCOUNT, RuntimeError("boom")),
            lambda: health.reset(),
        ):
            cache.set(health.UNREAD_CACHE_KEY, 9)

            record()

            self.assertIsNone(cache.get(health.UNREAD_CACHE_KEY))


# One load of the states: its SELECT inside a savepoint (``states_for`` runs in ``transaction.atomic``).
LOAD = 3


class RequestScopeTests(HealthCase):
    """``request_scope``: one inbox request loads each account's state once, and sees what it records itself."""

    def setUp(self):
        super().setUp()
        state(ACCOUNT, status=Status.OK, snapshot_at=self.now, messages=[{"uid": "1"}])

    def test_states_are_loaded_once_per_scope(self):
        with health.request_scope():
            with self.assertNumQueries(LOAD):
                first = health.states_for([ACCOUNT, GRAPH])
            with self.assertNumQueries(0):
                again = health.states_for([ACCOUNT])
                health.fresh_snapshot(ACCOUNT, 30)
                health.hidden_keys([ACCOUNT, GRAPH])

        self.assertEqual(list(first), [ACCOUNT.key])
        self.assertIs(again[ACCOUNT.key], first[ACCOUNT.key])

    def test_without_a_scope_every_call_reads_the_database(self):
        with self.assertNumQueries(2 * LOAD):
            health.states_for([ACCOUNT])
            health.states_for([ACCOUNT])

    def test_a_record_in_the_scope_replaces_the_loaded_state(self):
        with health.request_scope():
            health.states_for([ACCOUNT, GRAPH])
            health.record_failure(ACCOUNT, RuntimeError("boom"))
            health.record_ok(GRAPH)
            with self.assertNumQueries(0):
                states = health.states_for([ACCOUNT, GRAPH])

        self.assertEqual(states[ACCOUNT.key].status, Status.UNREACHABLE)
        self.assertEqual(states[GRAPH.key].status, Status.OK)

    def test_a_reset_or_a_failed_write_forgets_what_the_scope_loaded(self):
        with health.request_scope():
            health.states_for([ACCOUNT])
            health.reset()
            with self.assertNumQueries(LOAD):
                self.assertEqual(health.states_for([ACCOUNT])[ACCOUNT.key].status, Status.UNKNOWN)
            with (
                patch.object(InboxAccountState.objects, "select_for_update", side_effect=DatabaseError("locked")),
                self.assertLogs(LOGGER, "ERROR"),
            ):
                health.record_ok(ACCOUNT)
            with self.assertNumQueries(LOAD):
                health.states_for([ACCOUNT])

    def test_a_database_error_while_loading_is_logged_and_lists_nothing(self):
        with (
            health.request_scope(),
            patch.object(InboxAccountState.objects, "filter", side_effect=DatabaseError("down")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            self.assertEqual(health.states_for([ACCOUNT]), {})
