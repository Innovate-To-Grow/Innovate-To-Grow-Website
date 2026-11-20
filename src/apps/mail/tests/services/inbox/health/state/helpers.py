"""Fixtures for the ``inbox.health`` tests: sample accounts, state rows, snapshot messages, and a clean cache."""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.reading.accounts import InboxAccount

Status = InboxAccountState.Status
ACCOUNT = InboxAccount("imap:a", "imap", "a@gmail.com", "imap.gmail.com")
GRAPH = InboxAccount("graph:b@contoso.com", "graph", "b@contoso.com", "Microsoft Graph")
GRAPH_OTHER = InboxAccount("graph:c@contoso.com", "graph", "c@contoso.com", "Microsoft Graph")
LOGGER = "apps.mail.services.inbox.polling.health"


def state(account, **fields):
    return InboxAccountState.objects.create(account_key=account.key, address=account.address, **fields)


def messages(count, *, unread_every=0):
    return [{"uid": str(index), "is_seen": not (unread_every and index % unread_every == 0)} for index in range(count)]


class HealthCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.now = timezone.now()
