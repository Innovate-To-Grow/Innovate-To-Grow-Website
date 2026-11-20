"""Fixtures for the ``inbox.polling`` tests: a fake IMAP mailbox and a poll case over Graph + Gmail."""

import re
from contextlib import contextmanager
from unittest.mock import patch

from django.test import TestCase

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import poller as polling
from apps.mail.tests.services.delivery.graph_inbox.helpers import graph_config
from apps.mail.tests.services.inbox.accounts.helpers import (
    LIST_TARGET,
    UniversalInboxMixin,
    gmail_account,
    imap_message,
)

Status = InboxAccountState.Status
LOGGER = "apps.mail.services.inbox.polling.poller"


class FakeMailbox:
    """An IMAP session over ``messages`` (uid -> message): ``uids`` answers the two searches the poller runs,
    ``fetch`` returns the requested uids that still exist, and ``fetch("ALL")`` answers a live list read."""

    def __init__(self, uids, *, unseen=(), deleted=()):
        self.messages = {str(uid): imap_message(str(uid), 1 + int(uid) % 28, subject=f"Mail {uid}") for uid in uids}
        self.unseen = {str(uid) for uid in unseen}
        self.deleted = {str(uid) for uid in deleted}
        self.searches, self.fetched, self.fetch_kwargs = [], [], []
        self.opened = []

    def uids(self, criteria):
        self.searches.append(str(criteria))
        if criteria == "ALL":
            return sorted(self.messages, key=int)
        return sorted(self.unseen, key=int)

    def fetch(self, criteria, *, limit=None, reverse=False, **kwargs):
        if criteria == "ALL":
            # The inbox's own live list read (``messages._read_list``), not the poller's.
            present = [uid for uid in sorted(self.messages, key=int) if uid not in self.deleted]
            return [self.messages[uid] for uid in (present[::-1] if reverse else present)][:limit]
        requested = re.fullmatch(r"\(UID ([\d,]+)\)", str(criteria)).group(1).split(",")
        self.fetched.append(requested)
        self.fetch_kwargs.append(kwargs)
        return [self.messages[uid] for uid in requested if uid not in self.deleted]

    @contextmanager
    def __call__(self, mailbox=None, folder="INBOX", *, account=None):
        self.opened.append((account.key, folder))
        yield self


class PollCase(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"

    def use_mailbox(self, mailbox):
        self.open_inbox.side_effect = mailbox
        return mailbox

    def row(self, key):
        return InboxAccountState.objects.get(account_key=key)

    def poll(self, graph=None, **kwargs):
        graph_kwargs = {"side_effect": graph} if isinstance(graph, BaseException) else {"return_value": graph or []}
        with patch(LIST_TARGET, autospec=True, **graph_kwargs) as graph_list:
            result = polling.poll_accounts(**kwargs)
        self.graph_list = graph_list
        return result
