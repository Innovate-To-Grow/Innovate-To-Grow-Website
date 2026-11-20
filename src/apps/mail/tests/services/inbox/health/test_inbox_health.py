"""``inbox.health``: what every container knows about each inbox account (``InboxAccountState``): whether it
connected, which accounts the inbox hides, the poller's snapshot, and the sidebar's unread count."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox import health
from apps.mail.services.inbox.accounts import InboxAccount
from apps.mail.services.inbox.connection import InboxBusy, InboxError
from apps.mail.tests.services.inbox.accounts.helpers import UniversalInboxMixin, gmail_account

Status = InboxAccountState.Status
ACCOUNT = InboxAccount("imap:a", "imap", "a@gmail.com", "imap.gmail.com")
GRAPH = InboxAccount("graph:b@contoso.com", "graph", "b@contoso.com", "Microsoft Graph")
GRAPH_OTHER = InboxAccount("graph:c@contoso.com", "graph", "c@contoso.com", "Microsoft Graph")
LOGGER = "apps.mail.services.inbox.health"


def state(account, **fields):
    return InboxAccountState.objects.create(account_key=account.key, address=account.address, **fields)


def messages(count, *, unread_every=0):
    return [{"uid": str(index), "is_seen": not (unread_every and index % unread_every == 0)} for index in range(count)]


class HealthCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.now = timezone.now()


class PollIntervalTests(HealthCase):
    def test_three_minutes_by_default(self):
        self.assertEqual(health.poll_interval_seconds(), 180)
        self.assertEqual(health.snapshot_max_age(), timedelta(seconds=420))

    def test_the_setting_is_honoured_but_never_below_a_minute(self):
        for value, expected in ((300, 300), ("240", 240), (30, 60), (60, 60)):
            with self.subTest(value=value), override_settings(MAIL_INBOX_POLL_SECONDS=value):
                self.assertEqual(health.poll_interval_seconds(), expected)

    def test_zero_or_less_switches_polling_off_and_snapshots_age_as_by_default(self):
        for value in (0, -5):
            with self.subTest(value=value), override_settings(MAIL_INBOX_POLL_SECONDS=value):
                self.assertEqual(health.poll_interval_seconds(), 0)
                self.assertEqual(health.snapshot_max_age(), timedelta(seconds=420))

    @override_settings(MAIL_INBOX_POLL_SECONDS=300)
    def test_a_snapshot_lives_two_intervals_and_a_minute(self):
        self.assertEqual(health.snapshot_max_age(), timedelta(seconds=660))


class HiddenKeysTests(HealthCase):
    def test_an_account_unreachable_recently_is_hidden(self):
        state(ACCOUNT, status=Status.UNREACHABLE, checked_at=self.now - timedelta(minutes=1))

        self.assertEqual(health.hidden_keys([ACCOUNT, GRAPH], now=self.now), {ACCOUNT.key})

    def test_it_is_shown_again_once_the_retry_window_has_passed(self):
        state(ACCOUNT, status=Status.UNREACHABLE, checked_at=self.now - health.UNREACHABLE_RETRY - timedelta(seconds=1))

        self.assertEqual(health.hidden_keys([ACCOUNT], now=self.now), set())

    def test_the_window_edge_still_hides(self):
        state(ACCOUNT, status=Status.UNREACHABLE, checked_at=self.now - health.UNREACHABLE_RETRY)

        self.assertEqual(health.hidden_keys([ACCOUNT], now=self.now), {ACCOUNT.key})

    def test_busy_ok_unknown_and_unchecked_accounts_are_shown(self):
        recent = self.now - timedelta(seconds=5)
        state(ACCOUNT, status=Status.BUSY, checked_at=recent)
        state(GRAPH, status=Status.OK, checked_at=recent)
        state(GRAPH_OTHER, status=Status.UNREACHABLE, checked_at=None)

        self.assertEqual(health.hidden_keys([ACCOUNT, GRAPH, GRAPH_OTHER], now=self.now), set())

    def test_only_the_named_accounts_are_considered(self):
        state(ACCOUNT, status=Status.UNREACHABLE, checked_at=self.now)

        self.assertEqual(health.hidden_keys([GRAPH]), set())
        self.assertEqual(health.hidden_keys([]), set())

    def test_an_unreadable_state_table_hides_nothing(self):
        state(ACCOUNT, status=Status.UNREACHABLE, checked_at=self.now)

        with (
            patch.object(InboxAccountState.objects, "filter", side_effect=DatabaseError("gone")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            self.assertEqual(health.hidden_keys([ACCOUNT]), set())


class FreshSnapshotTests(HealthCase):
    def test_a_fresh_snapshot_is_sliced_to_the_limit(self):
        state(ACCOUNT, status=Status.OK, snapshot_at=self.now - timedelta(minutes=1), messages=messages(5))

        self.assertEqual([m["uid"] for m in health.fresh_snapshot(ACCOUNT, 3, now=self.now)], ["0", "1", "2"])

    def test_a_held_back_account_still_serves_its_fresh_snapshot(self):
        state(ACCOUNT, status=Status.BUSY, snapshot_at=self.now, messages=messages(2))

        self.assertEqual(len(health.fresh_snapshot(ACCOUNT, 30, now=self.now)), 2)

    def test_an_empty_fresh_snapshot_is_an_empty_list(self):
        state(ACCOUNT, status=Status.OK, snapshot_at=self.now, messages=[])

        self.assertEqual(health.fresh_snapshot(ACCOUNT, 30, now=self.now), [])

    def test_a_stale_snapshot_is_none(self):
        state(
            ACCOUNT,
            status=Status.OK,
            snapshot_at=self.now - health.snapshot_max_age() - timedelta(seconds=1),
            messages=messages(2),
        )

        self.assertIsNone(health.fresh_snapshot(ACCOUNT, 30, now=self.now))

    def test_an_unreachable_account_has_none(self):
        state(ACCOUNT, status=Status.UNREACHABLE, snapshot_at=self.now, messages=messages(2))

        self.assertIsNone(health.fresh_snapshot(ACCOUNT, 30, now=self.now))

    def test_a_limit_larger_than_the_snapshot_keeps_is_none(self):
        state(ACCOUNT, status=Status.OK, snapshot_at=self.now, messages=messages(50))

        self.assertEqual(len(health.fresh_snapshot(ACCOUNT, health.SNAPSHOT_LIMIT, now=self.now)), 50)
        self.assertIsNone(health.fresh_snapshot(ACCOUNT, health.SNAPSHOT_LIMIT + 1, now=self.now))

    def test_no_state_or_no_snapshot_is_none(self):
        self.assertIsNone(health.fresh_snapshot(ACCOUNT, 30))
        state(ACCOUNT, status=Status.OK, checked_at=self.now)

        self.assertIsNone(health.fresh_snapshot(ACCOUNT, 30))

    def test_the_last_snapshot_is_served_however_old_or_unreachable(self):
        self.assertIsNone(health.last_snapshot(ACCOUNT, 30))
        state(ACCOUNT, status=Status.UNREACHABLE, snapshot_at=self.now - timedelta(days=3), messages=messages(4))

        self.assertEqual([m["uid"] for m in health.last_snapshot(ACCOUNT, 2)], ["0", "1"])

    def test_without_a_snapshot_there_is_no_last_one(self):
        state(ACCOUNT, status=Status.OK)

        self.assertIsNone(health.last_snapshot(ACCOUNT, 30))


class OtherMailboxStateTests(HealthCase):
    """A state recorded for another address (the account's row now reads another mailbox) is ignored everywhere."""

    def setUp(self):
        super().setUp()
        self.row = InboxAccountState.objects.create(
            account_key=ACCOUNT.key,
            address="previous@gmail.com",
            status=Status.UNREACHABLE,
            checked_at=self.now,
            snapshot_at=self.now,
            messages=messages(3),
            unread_count=3,
        )

    def test_it_is_not_a_state_of_the_account(self):
        self.assertEqual(health.states_for([ACCOUNT]), {})
        self.assertFalse(health.same_mailbox(self.row, ACCOUNT))

    def test_it_neither_hides_the_account_nor_serves_its_snapshot(self):
        InboxAccountState.objects.filter(pk=self.row.pk).update(status=Status.OK)

        self.assertIsNone(health.fresh_snapshot(ACCOUNT, 30, now=self.now))
        self.assertIsNone(health.last_snapshot(ACCOUNT, 30))
        InboxAccountState.objects.filter(pk=self.row.pk).update(status=Status.UNREACHABLE)
        self.assertEqual(health.hidden_keys([ACCOUNT], now=self.now), set())

    def test_a_blank_address_is_another_mailbox(self):
        InboxAccountState.objects.filter(pk=self.row.pk).update(address="")

        self.assertEqual(health.states_for([ACCOUNT]), {})

    def test_the_address_matches_ignoring_case_and_spaces(self):
        InboxAccountState.objects.filter(pk=self.row.pk).update(address="  A@Gmail.COM ")

        self.assertEqual(list(health.states_for([ACCOUNT])), [ACCOUNT.key])
        self.assertEqual(health.hidden_keys([ACCOUNT], now=self.now), {ACCOUNT.key})

    def test_a_new_read_records_the_current_mailbox(self):
        health.record_ok(ACCOUNT, messages=messages(1), now=self.now)

        self.row.refresh_from_db()
        self.assertEqual((self.row.address, len(self.row.messages)), (ACCOUNT.address, 1))
        self.assertEqual(list(health.states_for([ACCOUNT])), [ACCOUNT.key])


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
            lambda: health.mark_seen(ACCOUNT, "1"),
            lambda: health.reset(),
        ):
            cache.set(health.UNREAD_CACHE_KEY, 9)

            record()

            self.assertIsNone(cache.get(health.UNREAD_CACHE_KEY))


class MarkSeenTests(HealthCase):
    def setUp(self):
        super().setUp()
        self.row = state(
            ACCOUNT,
            status=Status.OK,
            snapshot_at=self.now,
            messages=[{"uid": "1", "is_seen": False}, {"uid": "2", "is_seen": False}, {"uid": "3", "is_seen": True}],
            unread_count=2,
        )

    def test_an_opened_message_is_read_in_the_snapshot(self):
        health.mark_seen(ACCOUNT, "1")

        self.row.refresh_from_db()
        self.assertEqual([m["is_seen"] for m in self.row.messages], [True, False, True])
        self.assertEqual(self.row.unread_count, 1)

    def test_an_unknown_or_already_read_message_changes_nothing(self):
        before = self.row.updated_at
        for uid in ("3", "99"):
            health.mark_seen(ACCOUNT, uid)

        self.row.refresh_from_db()
        self.assertEqual((self.row.unread_count, self.row.updated_at), (2, before))

    def test_an_account_without_a_state_is_ignored(self):
        health.mark_seen(GRAPH, "1")

        self.assertFalse(InboxAccountState.objects.filter(account_key=GRAPH.key).exists())

    def test_a_database_error_is_logged(self):
        with (
            patch.object(InboxAccountState.objects, "select_for_update", side_effect=DatabaseError("locked")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            health.mark_seen(ACCOUNT, "1")

        self.row.refresh_from_db()
        self.assertEqual(self.row.unread_count, 2)


class ResetAndPruneTests(HealthCase):
    def setUp(self):
        super().setUp()
        for account in (ACCOUNT, GRAPH, GRAPH_OTHER):
            state(account, status=Status.UNREACHABLE, detail="Could not connect", checked_at=self.now)

    def statuses(self):
        return dict(InboxAccountState.objects.values_list("account_key", "status"))

    def test_reset_by_key(self):
        health.reset([ACCOUNT.key])

        self.assertEqual(
            self.statuses(),
            {ACCOUNT.key: Status.UNKNOWN, GRAPH.key: Status.UNREACHABLE, GRAPH_OTHER.key: Status.UNREACHABLE},
        )
        self.assertEqual(InboxAccountState.objects.get(account_key=ACCOUNT.key).detail, "")
        self.assertEqual(health.hidden_keys([ACCOUNT, GRAPH]), {GRAPH.key})

    def test_reset_by_prefix(self):
        health.reset(prefix="graph:")

        self.assertEqual(
            self.statuses(),
            {ACCOUNT.key: Status.UNREACHABLE, GRAPH.key: Status.UNKNOWN, GRAPH_OTHER.key: Status.UNKNOWN},
        )

    def test_reset_everything(self):
        health.reset()

        self.assertEqual(set(self.statuses().values()), {Status.UNKNOWN})

    def test_reset_with_no_keys_resets_nothing(self):
        health.reset([])

        self.assertEqual(set(self.statuses().values()), {Status.UNREACHABLE})

    def test_reset_never_raises(self):
        with (
            patch.object(InboxAccountState.objects, "exclude", side_effect=DatabaseError("locked")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            health.reset()

    def test_prune_deletes_the_states_of_accounts_no_longer_read(self):
        self.assertEqual(health.prune([ACCOUNT]), 2)

        self.assertEqual(list(InboxAccountState.objects.values_list("account_key", flat=True)), [ACCOUNT.key])

    def test_with_no_account_every_state_is_pruned(self):
        self.assertEqual(health.prune([]), 3)
        self.assertFalse(InboxAccountState.objects.exists())


class UnreadTotalTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.ok, self.down, self.new = (
            gmail_account("ok@gmail.com"),
            gmail_account("down@gmail.com", is_active=False, show_in_inbox=True),
            gmail_account("new@gmail.com", is_active=False, show_in_inbox=True),
        )
        InboxAccountState.objects.create(
            account_key=f"imap:{self.ok.pk}", address="ok@gmail.com", status=Status.OK, snapshot_at=now, unread_count=3
        )
        InboxAccountState.objects.create(
            account_key=f"imap:{self.down.pk}",
            address="down@gmail.com",
            status=Status.UNREACHABLE,
            snapshot_at=now,
            unread_count=5,
        )
        # Counted only once a snapshot was taken.
        InboxAccountState.objects.create(
            account_key=f"imap:{self.new.pk}", address="new@gmail.com", status=Status.OK, unread_count=4
        )
        # An account the inbox no longer reads.
        InboxAccountState.objects.create(
            account_key="imap:gone", address="gone@gmail.com", status=Status.OK, snapshot_at=now, unread_count=7
        )

    def test_counts_the_accounts_that_connect_and_caches_it(self):
        self.assertEqual(health.unread_total(), 3)
        self.assertEqual(cache.get(health.UNREAD_CACHE_KEY), 3)

        # Served from the cache: a queryset update records nothing.
        InboxAccountState.objects.filter(account_key=f"imap:{self.ok.pk}").update(unread_count=10)
        self.assertEqual(health.unread_total(), 3)

        cache.delete(health.UNREAD_CACHE_KEY)
        self.assertEqual(health.unread_total(), 10)

    def test_a_busy_account_still_counts(self):
        InboxAccountState.objects.filter(account_key=f"imap:{self.down.pk}").update(status=Status.BUSY)

        self.assertEqual(health.unread_total(), 8)

    def test_a_state_recorded_for_another_mailbox_is_not_counted(self):
        InboxAccountState.objects.filter(account_key=f"imap:{self.ok.pk}").update(address="previous@gmail.com")

        self.assertEqual(health.unread_total(), 0)

    def test_an_account_listing_failure_counts_nothing_and_is_not_cached(self):
        with (
            patch("apps.mail.services.inbox.accounts.readable_accounts", side_effect=InboxError("no tables")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            self.assertEqual(health.unread_total(), 0)

        self.assertIsNone(cache.get(health.UNREAD_CACHE_KEY))
