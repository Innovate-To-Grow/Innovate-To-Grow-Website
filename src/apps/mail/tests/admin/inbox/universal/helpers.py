"""Fixtures for the universal inbox admin views: two accounts, two senders, sample messages, and a view case
that patches the inbox services the views call."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.services.inbox import InboxAccount, InboxListing, SendIdentity

SERVICES = "apps.mail.admin.inbox.services"
GRAPH = InboxAccount("graph:i2g@contoso.com", "graph", "i2g@contoso.com", "Microsoft Graph")
IMAP = InboxAccount("imap:7", "imap", "i2g@gmail.com", "imap.gmail.com", 7)
DEFAULT = SendIdentity("default", "notify@ucmerced.edu", "ses", "Notification Delivery · AWS SES")
IMAP_SENDER = SendIdentity("imap:7", "i2g@gmail.com", "gmail_smtp", "SMTP · smtp.gmail.com", 7)


def summary(uid, account, **overrides):
    return {
        "uid": uid,
        "from_name": "Pat Lee",
        "from_email": "pat@example.com",
        "to": [],
        "subject": f"Subject {uid}",
        "snippet": "Body",
        "date": "2026-01-01",
        "timestamp": 1.0,
        "is_seen": True,
        "from_own_mailbox": False,
        "account": account.key,
        "account_address": account.address,
    } | overrides


def detail(account=IMAP, **overrides):
    return {
        "uid": "42",
        "from_name": "Pat Lee",
        "from_email": "pat@example.com",
        "to": [{"name": "", "email": account.address}],
        "subject": "Question",
        "date": "2026-01-01",
        "html": "<p>Hello team.</p>",
        "text": "Hello team.",
        "message_id": "<msg@example.com>",
        "references": "",
        "reply_to": "",
        "return_path": "",
        "authentication_results": "",
        "from_own_mailbox": False,
        "account": account.key,
        "account_address": account.address,
    } | overrides


class UniversalInboxViewCase(TestCase):
    accounts = [GRAPH, IMAP]

    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.hidden = []
        self.connectable = self.patch("connectable_accounts", side_effect=self.connectable_accounts)
        self.list_one = self.patch("list_inbox_messages", return_value=[summary("1", IMAP)])
        self.list_all = self.patch(
            "list_all_inbox_messages", return_value=InboxListing(messages=[summary("g1", GRAPH), summary("1", IMAP)])
        )

    def connectable_accounts(self, *, retry=False):
        hidden = [] if retry else list(self.hidden)
        return [item for item in self.accounts if item not in hidden], hidden

    def patch(self, name, **kwargs):
        patcher = patch(f"{SERVICES}.{name}", **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def fragment(self, query=""):
        return self.client.get(reverse("admin:mail_inbox_fragment") + query)
