"""One inbox fragment request loads the accounts' ``InboxAccountState`` rows once, however many accounts there are
(it used to load them three times, plus once more per account)."""

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.models import EmailServiceConfig, GmailAccessAccount, MicrosoftGraphProviderConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.reading.accounts import readable_accounts

STATE_TABLE = InboxAccountState._meta.db_table
# The request with every account served from its fresh snapshot: the session and user, the account configuration
# (Graph config and the Gmail rows), and one load of the states (a SELECT inside a savepoint).
EXPECTED_QUERIES = 7


def snapshot(uid, address):
    return {
        "uid": str(uid),
        "subject": f"Subject {uid}",
        "from_name": "Pat Lee",
        "from_email": "pat@example.com",
        "to": [],
        "date": "2026-10-01",
        "timestamp": float(uid),
        "snippet": "Body",
        "is_seen": uid % 2 == 0,
        "account_address": address,
    }


class FragmentQueryCountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        EmailServiceConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        GmailAccessAccount.objects.all().delete()
        self.client.force_login(make_superuser())

    def add_accounts(self, count):
        start = GmailAccessAccount.objects.count()
        for index in range(start, start + count):
            address = f"inbox{index}@example.com"
            row = GmailAccessAccount.objects.create(
                name=address,
                is_active=index == 0,
                show_in_inbox=True,
                imap_host="imap.gmail.com",
                gmail_username=address,
                gmail_password="app-password",
            )
            messages = [{**snapshot(uid, address), "account": f"imap:{row.pk}"} for uid in range(1, 6)]
            InboxAccountState.objects.create(
                account_key=f"imap:{row.pk}",
                address=address,
                status=InboxAccountState.Status.OK,
                snapshot_at=timezone.now(),
                messages=messages,
                unread_count=3,
            )

    def fragment(self):
        cache.clear()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("admin:mail_inbox_fragment"))
        self.assertEqual(response.status_code, 200)
        return response, queries

    def state_loads(self, queries):
        return [query for query in queries.captured_queries if STATE_TABLE in query["sql"]]

    def test_the_states_are_loaded_once_whatever_the_number_of_accounts(self):
        self.add_accounts(1)
        _response, one = self.fragment()
        self.add_accounts(2)
        self.assertEqual(len(readable_accounts(use_cache=False)), 3)

        response, three = self.fragment()

        self.assertEqual(len(self.state_loads(one)), 1)
        self.assertEqual(len(self.state_loads(three)), 1)
        self.assertEqual(len(three), len(one))
        self.assertContains(response, "inbox2@example.com")

    def test_the_fragment_query_count(self):
        self.add_accounts(3)
        self.client.get(reverse("admin:mail_inbox_fragment"))  # the session is saved once
        cache.clear()

        with self.assertNumQueries(EXPECTED_QUERIES):
            response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertContains(response, 'data-uid="imap:', count=15)
