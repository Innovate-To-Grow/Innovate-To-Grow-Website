"""``inbox.health``: the sidebar's unread count across the accounts that connect."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.reading.connection import InboxError
from apps.mail.tests.services.inbox.accounts.helpers import UniversalInboxMixin, gmail_account
from apps.mail.tests.services.inbox.health.state.helpers import (
    LOGGER,
    Status,
)


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
            patch("apps.mail.services.inbox.reading.accounts.readable_accounts", side_effect=InboxError("no tables")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            self.assertEqual(health.unread_total(), 0)

        self.assertIsNone(cache.get(health.UNREAD_CACHE_KEY))
