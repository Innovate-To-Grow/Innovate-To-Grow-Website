"""``inbox.health``: what every container knows about each inbox account (``InboxAccountState``): the poll
interval, which accounts the inbox hides, and the poller's snapshot."""

from datetime import timedelta
from unittest.mock import patch

from django.db import DatabaseError
from django.test import override_settings

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.tests.services.inbox.health.state.helpers import (
    ACCOUNT,
    GRAPH,
    GRAPH_OTHER,
    LOGGER,
    HealthCase,
    Status,
    messages,
    state,
)


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
