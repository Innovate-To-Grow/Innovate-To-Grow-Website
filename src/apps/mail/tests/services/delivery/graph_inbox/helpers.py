"""Shared Microsoft Graph inbox fixtures: the scoped mailbox, sample Graph payloads, and the fixture mixin."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache

from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import create_graph_config

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MAILBOX = "i2g@contoso.com"
MESSAGE_ID = "AAMkAGI2THVSAAA="
SUMMARY_KEYS = {
    "uid", "subject", "from_name", "from_email", "to", "date", "timestamp", "snippet", "is_seen", "from_own_mailbox",
}  # fmt: skip
DETAIL_KEYS = {
    "uid", "subject", "from_name", "from_email", "to", "date", "timestamp", "html", "text",
    "message_id", "references", "reply_to", "return_path", "authentication_results", "from_own_mailbox",
}  # fmt: skip
# What the inbox services add to every summary / detail: the account each message was read from.
ACCOUNT_KEYS = {"account", "account_address"}
GRAPH_MESSAGE = {
    "id": MESSAGE_ID,
    "subject": "  Event question  ",
    "from": {"emailAddress": {"name": "Ada Lovelace", "address": "ada@example.com"}},
    "toRecipients": [
        {"emailAddress": {"name": "I2G", "address": MAILBOX}},
        {"emailAddress": {"address": "cc@example.com"}},
        "not a recipient",
    ],
    "receivedDateTime": "2026-10-20T15:30:00Z",
    "bodyPreview": "Hello\n\n  there   friend",
    "isRead": True,
}
RAW_MIME = b"""From: "Ada Lovelace" <ada@example.com>
To: I2G <i2g@contoso.com>, cc@example.com
Subject: Re: Event question
Date: Tue, 20 Oct 2026 15:30:00 +0000
Message-ID: <reply-1@example.com>
References: <root@example.com> <orig@example.com>
Reply-To: Replies <Replies@Example.com>
Return-Path: <Bounce@Example.com>
Authentication-Results: mx.contoso.com; spf=pass
Authentication-Results: mx.contoso.com; dkim=pass
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="b1"

--b1
Content-Type: text/plain; charset="utf-8"

Plain body
--b1
Content-Type: text/html; charset="utf-8"

<p>HTML body</p>
--b1--
"""


def imap_message(**overrides):
    values = {
        "uid": "7",
        "subject": "s",
        "from_values": None,
        "from_": "x@example.com",
        "to_values": [],
        "date": None,
        "html": "",
        "text": "",
        "flags": (),
        "headers": {},
    }
    return SimpleNamespace(**{**values, **overrides})


def graph_config(permission=Permission.SEND_AND_READ, **overrides):
    values = {
        "name": "Graph",
        "is_active": True,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
    }
    return create_graph_config(scope=(MAILBOX,), permission=permission, **{**values, **overrides})


LIST_TARGET = "apps.core.services.email.graph.mailbox.GraphMailboxReader.list_messages"
FETCH_TARGET = "apps.core.services.email.graph.mailbox.GraphMailboxReader.fetch_mime"
OPEN_INBOX = "apps.mail.services.inbox._open_inbox"
GRAPH_KEY = f"graph:{MAILBOX}"


class GraphInboxFixtureMixin:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        EmailServiceConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        EmailServiceConfig.objects.create(name="Prod", is_active=True, provider="graph", from_email=MAILBOX)
        # Gmail IMAP must never be opened while Graph serves the inbox.
        patcher = patch(OPEN_INBOX, side_effect=AssertionError("IMAP was opened"))
        self.open_inbox = patcher.start()
        self.addCleanup(patcher.stop)
