"""Fixtures for the snapshot listing tests: snapshot messages and a case over Graph + Gmail with state helpers."""

from django.test import TestCase
from django.utils import timezone

from apps.mail.models import InboxAccountState
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX, graph_config
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    UniversalInboxMixin,
    gmail_account,
    graph_message,
    imap_message,
)

Status = InboxAccountState.Status
GRAPH_MESSAGES = [graph_message("g-20", "2026-10-20T12:00:00Z")]


def snapshot_message(uid, account_key, address, timestamp=1.0, **overrides):
    return {
        "uid": uid,
        "subject": f"Snapshot {uid}",
        "timestamp": timestamp,
        "is_seen": False,
        "account": account_key,
        "account_address": address,
    } | overrides


class SnapshotCase(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"
        self.imap.answer(self.imap_key, [imap_message("i-21", 21), imap_message("i-19", 19)])
        self.now = timezone.now()

    def state(self, key, **fields):
        """A state recorded for the mailbox ``key`` reads now (unless ``address`` says otherwise)."""
        fields.setdefault("address", MAILBOX if key == GRAPH_KEY else "i2g@gmail.com")
        return InboxAccountState.objects.create(account_key=key, **fields)

    def fresh(self, key, address, uids, **fields):
        return self.state(
            key,
            address=address,
            status=Status.OK,
            snapshot_at=self.now,
            messages=[snapshot_message(uid, key, address) for uid in uids],
            **fields,
        )

    def row(self, key):
        return InboxAccountState.objects.get(account_key=key)
