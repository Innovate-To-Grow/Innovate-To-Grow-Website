"""Fixtures for the universal inbox: a Graph mailbox scope, Gmail IMAP rows, and fake reads of both.

Nothing here reaches a mailbox: Graph reads are ``GraphMailboxReader`` methods patched by the tests, and IMAP
sessions are a fake ``_open_inbox`` that answers per account.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache

from apps.core.models import EmailServiceConfig, GmailAccessAccount, MicrosoftGraphProviderConfig
from apps.mail.services.inbox.reading.connection import InboxError
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX

LIST_TARGET = "apps.core.services.email.graph.mailbox.GraphMailboxReader.list_messages"
FETCH_TARGET = "apps.core.services.email.graph.mailbox.GraphMailboxReader.fetch_mime"
OPEN_INBOX = "apps.mail.services.inbox._open_inbox"
GRAPH_KEY = f"graph:{MAILBOX}"


def gmail_account(username="i2g@gmail.com", **overrides):
    """A configured Gmail IMAP access account (active unless overridden)."""
    values = {
        "name": username,
        "is_active": True,
        "imap_host": "imap.gmail.com",
        "gmail_username": username,
        "gmail_password": "app-password",
    }
    return GmailAccessAccount.objects.create(**{**values, **overrides})


def graph_message(uid, received, subject="Graph mail"):
    return {
        "id": uid,
        "subject": subject,
        "from": {"emailAddress": {"name": "Ada", "address": "ada@example.com"}},
        "toRecipients": [],
        "receivedDateTime": received,
        "bodyPreview": "Hello",
        "isRead": False,
    }


GRAPH_MESSAGES = [
    graph_message("g-20", "2026-10-20T12:00:00Z"),
    graph_message("g-18", "2026-10-18T12:00:00Z"),
]


def imap_message(uid, day, subject="IMAP mail"):
    return SimpleNamespace(
        uid=uid,
        subject=subject,
        from_values=SimpleNamespace(name="Bob", email="bob@example.com"),
        from_="bob@example.com",
        to_values=[],
        date=datetime(2026, 10, day, 12, 0, tzinfo=UTC),
        html="",
        text="Hello",
        flags=(),
        headers={},
    )


class FakeImap:
    """Stands in for ``inbox._open_inbox``: each account key answers with its messages, or raises its error."""

    def __init__(self):
        self.answers = {}
        self.opened = []

    def answer(self, key, messages=None, *, error=None):
        self.answers[key] = error if error is not None else list(messages or [])

    @contextmanager
    def __call__(self, mailbox=None, folder="INBOX", *, account=None):
        self.opened.append(account.key if account else None)
        answer = self.answers.get(account.key if account else None, InboxError("no fake answer"))
        if isinstance(answer, BaseException):
            raise answer
        client = MagicMock()
        client.fetch.side_effect = lambda *args, **kwargs: iter(answer)
        yield client


class UniversalInboxMixin:
    """A clean slate: Notification Delivery sends as the Graph mailbox, and no Graph or Gmail account exists yet."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        EmailServiceConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        GmailAccessAccount.objects.all().delete()
        EmailServiceConfig.objects.create(name="Prod", is_active=True, provider="graph", from_email=MAILBOX)
        self.imap = FakeImap()
        patcher = patch(OPEN_INBOX, side_effect=self.imap)
        self.open_inbox = patcher.start()
        self.addCleanup(patcher.stop)
