"""A refused Gmail sign-in is an account that cannot connect (``InboxBusy(refused=True)``), not one that must wait;
and the account and sender lists are cached briefly per container."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.services.delivery_rates import RateDeferred
from apps.mail.models import InboxAccountState
from apps.mail.services.inbox import health
from apps.mail.services.inbox.accounts import (
    ACCOUNTS_CACHE_KEY,
    connectable_accounts,
    forget_accounts,
    readable_accounts,
)
from apps.mail.services.inbox.connection import InboxBusy, _open_inbox
from apps.mail.services.inbox.senders import SENDERS_CACHE_KEY, forget_identities, send_identities
from apps.mail.tests.services.inbox.accounts.helpers import gmail_account
from apps.mail.tests.services.inbox.accounts.test_account_connection import account_for

SESSION = "apps.mail.services.campaign.gmail_import.session.gmail_imap_session"


def deferred(reason):
    now = timezone.now()
    return RateDeferred(now + timedelta(seconds=90), reason, now=now)


class RefusedSignInTests(TestCase):
    def setUp(self):
        cache.clear()
        self.account = account_for(gmail_account())

    def open_with(self, exc):
        with patch(SESSION, side_effect=exc), self.assertRaises(InboxBusy) as raised:
            with _open_inbox(account=self.account):
                pass
        return raised.exception

    def test_an_auth_breaker_is_a_refused_sign_in(self):
        busy = self.open_with(deferred("breaker:auth"))

        self.assertTrue(busy.refused)
        self.assertEqual(busy.retry_after, 90)
        self.assertIn("Gmail refused the sign-in", str(busy))

    def test_any_other_hold_is_only_a_wait(self):
        for reason in ("pace", "cooldown", "breaker:permission", "budget:daily"):
            with self.subTest(reason=reason):
                busy = self.open_with(deferred(reason))

                self.assertFalse(busy.refused)
                self.assertIn("Gmail is busy", str(busy))

    def test_a_refused_sign_in_hides_the_account_and_a_wait_does_not(self):
        health.record_failure(self.account, self.open_with(deferred("pace")))
        self.assertEqual(health.hidden_keys([self.account]), set())

        health.record_failure(self.account, self.open_with(deferred("breaker:auth")))
        self.assertEqual(health.hidden_keys([self.account]), {self.account.key})

    def test_inbox_busy_is_not_refused_by_default(self):
        self.assertFalse(InboxBusy("Gmail is busy.", 30).refused)


class AccountListCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.row = gmail_account()

    def test_the_list_is_cached_until_forgotten(self):
        first = readable_accounts()
        self.assertEqual(cache.get(ACCOUNTS_CACHE_KEY), first)

        with patch("apps.mail.services.inbox.accounts._imap_accounts") as imap_accounts:
            self.assertEqual(readable_accounts(), first)
            imap_accounts.assert_not_called()

            forget_accounts()
            imap_accounts.return_value = []
            self.assertEqual(readable_accounts(), [])

    def test_use_cache_false_reads_the_configuration_and_refreshes_the_cache(self):
        cache.set(ACCOUNTS_CACHE_KEY, [], 60)

        accounts = readable_accounts(use_cache=False)

        self.assertEqual([account.key for account in accounts], [f"imap:{self.row.pk}"])
        self.assertEqual(cache.get(ACCOUNTS_CACHE_KEY), accounts)

    def test_a_cached_list_is_a_copy(self):
        readable_accounts().clear()

        self.assertEqual(len(readable_accounts()), 1)

    def test_connectable_accounts_splits_off_those_that_could_not_connect(self):
        other = gmail_account("other@gmail.com", is_active=False, show_in_inbox=True)
        InboxAccountState.objects.create(
            account_key=f"imap:{other.pk}",
            address="other@gmail.com",
            status=InboxAccountState.Status.UNREACHABLE,
            checked_at=timezone.now(),
        )

        shown, hidden = connectable_accounts()
        retried, none_hidden = connectable_accounts(retry=True)

        self.assertEqual(
            ([a.key for a in shown], [a.key for a in hidden]), ([f"imap:{self.row.pk}"], [f"imap:{other.pk}"])
        )
        self.assertEqual((len(retried), none_hidden), (2, []))


class SenderListCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_the_identities_are_cached_until_forgotten(self):
        with patch("apps.mail.services.inbox.senders._collect", return_value=["first"]) as collect:
            self.assertEqual(send_identities(), ["first"])
            collect.return_value = ["second"]

            self.assertEqual(send_identities(), ["first"])
            self.assertEqual(send_identities(use_cache=False), ["second"])
            self.assertEqual(cache.get(SENDERS_CACHE_KEY), ["second"])

            forget_identities()
            collect.return_value = ["third"]
            self.assertEqual(send_identities(), ["third"])

        self.assertEqual(collect.call_count, 3)
