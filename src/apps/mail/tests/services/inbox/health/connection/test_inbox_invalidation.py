"""``inbox.invalidation``: saving or deleting a mail configuration drops the cached account and sender lists, and
saving a mailbox's own configuration forgets whether it could connect."""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import (
    EmailServiceConfig,
    GmailApiSubject,
    MicrosoftGraphAccessCheck,
    MicrosoftGraphMailboxScope,
    MicrosoftGraphProviderConfig,
)
from apps.core.tests.gmail_api_helpers import make_config
from apps.core.tests.graph_helpers import grant
from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.reading.accounts import ACCOUNTS_CACHE_KEY, readable_accounts
from apps.mail.services.inbox.sending.senders import SENDERS_CACHE_KEY, send_identities
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX, Permission, graph_config
from apps.mail.tests.services.inbox.accounts.helpers import GRAPH_KEY, UniversalInboxMixin, gmail_account

Status = InboxAccountState.Status
WORKSPACE = "i2g@g.ucmerced.edu"


class InvalidationCase(UniversalInboxMixin, TestCase):
    def unreachable(self, key, address=None):
        """An account that could not connect just now (a Graph key names its own mailbox)."""
        address = address or key.removeprefix("graph:")
        return InboxAccountState.objects.create(
            account_key=key, address=address, status=Status.UNREACHABLE, checked_at=timezone.now()
        )

    def status(self, key):
        return InboxAccountState.objects.get(account_key=key).status

    def prime(self):
        """Fill both caches with a sentinel, as a page view would."""
        cache.set(ACCOUNTS_CACHE_KEY, ["cached"], 60)
        cache.set(SENDERS_CACHE_KEY, ["cached"], 60)

    def assert_forgotten(self):
        self.assertIsNone(cache.get(ACCOUNTS_CACHE_KEY))
        self.assertIsNone(cache.get(SENDERS_CACHE_KEY))


class GmailAccountInvalidationTests(InvalidationCase):
    def test_saving_an_account_drops_the_lists_and_shows_it_again(self):
        row = gmail_account()
        key = f"imap:{row.pk}"
        other = self.unreachable("imap:other", "other@gmail.com")
        self.unreachable(key, "i2g@gmail.com")
        self.assertEqual(health.hidden_keys(readable_accounts()), {key})
        self.prime()

        row.gmail_password = "fixed-password"
        row.save()

        self.assert_forgotten()
        self.assertEqual(self.status(key), Status.UNKNOWN)
        other.refresh_from_db()
        self.assertEqual(other.status, Status.UNREACHABLE)
        self.assertEqual(health.hidden_keys(readable_accounts()), set())

    def test_a_new_account_is_listed_at_once(self):
        self.assertEqual(readable_accounts(), [])

        row = gmail_account()

        self.assertEqual([account.key for account in readable_accounts()], [f"imap:{row.pk}"])

    def test_deleting_an_account_drops_the_lists(self):
        row = gmail_account()
        self.assertEqual(len(readable_accounts()), 1)
        self.prime()

        row.delete()

        self.assert_forgotten()
        self.assertEqual(readable_accounts(), [])


class GraphInvalidationTests(InvalidationCase):
    def setUp(self):
        super().setUp()
        self.config = graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"
        for key in (GRAPH_KEY, "graph:alpha@contoso.com"):
            self.unreachable(key)
        self.unreachable(self.imap_key, "i2g@gmail.com")
        self.prime()

    def test_saving_a_mailbox_scope_resets_every_graph_account(self):
        grant(self.config, "alpha@contoso.com", permission=Permission.READ)

        self.assert_forgotten()
        self.assertEqual(self.status(GRAPH_KEY), Status.UNKNOWN)
        self.assertEqual(self.status("graph:alpha@contoso.com"), Status.UNKNOWN)
        self.assertEqual(self.status(self.imap_key), Status.UNREACHABLE)
        self.assertIn("graph:alpha@contoso.com", [account.key for account in readable_accounts()])

    def test_deleting_a_scope_resets_them_too(self):
        MicrosoftGraphMailboxScope.objects.get(config=self.config, mailbox=MAILBOX).delete()

        self.assert_forgotten()
        self.assertEqual(self.status(GRAPH_KEY), Status.UNKNOWN)
        self.assertNotIn(GRAPH_KEY, [account.key for account in readable_accounts()])

    def test_saving_the_provider_config_resets_them(self):
        MicrosoftGraphProviderConfig.objects.get(pk=self.config.pk).save()

        self.assertEqual(self.status(GRAPH_KEY), Status.UNKNOWN)
        self.assertEqual(self.status(self.imap_key), Status.UNREACHABLE)

    def test_an_access_check_drops_the_lists_but_keeps_the_states(self):
        MicrosoftGraphAccessCheck.objects.create(
            config=self.config,
            certificate_sha1="0" * 40,
            tenant_id="tenant",
            client_id="client",
            deny_mailbox="deny@contoso.com",
            source=MicrosoftGraphAccessCheck.Source.choices[0][0],
            verdict=MicrosoftGraphAccessCheck.Verdict.choices[0][0],
        )

        self.assert_forgotten()
        self.assertEqual(self.status(GRAPH_KEY), Status.UNREACHABLE)


class SenderInvalidationTests(InvalidationCase):
    def test_saving_a_gmail_api_subject_drops_the_cached_senders(self):
        make_config(subjects=(WORKSPACE,), active=True)
        key = f"gmail_api:{WORKSPACE}"
        self.assertIn(key, [identity.key for identity in send_identities()])
        # A queryset update sends no signal: the cached list still offers the subject.
        GmailApiSubject.objects.update(verified_at=None)
        self.assertIn(key, [identity.key for identity in send_identities()])

        GmailApiSubject.objects.get(subject=WORKSPACE).save()

        self.assertIsNone(cache.get(SENDERS_CACHE_KEY))
        self.assertNotIn(key, [identity.key for identity in send_identities()])

    def test_saving_notification_delivery_drops_both_lists(self):
        self.prime()

        EmailServiceConfig.objects.get().save()

        self.assert_forgotten()
