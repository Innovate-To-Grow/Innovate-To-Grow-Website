from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.mail.services.gmail_import import (
    fetch_message_html_fragment,
    list_recent_sent_messages,
)
from apps.mail.services.gmail_import.credential_mail import WITHOUT_CREDENTIAL_MAIL

UNTAGGED = str(WITHOUT_CREDENTIAL_MAIL)


class _FakeMailbox:
    def __init__(self, messages):
        self.messages = messages
        self.fetch_calls = []

    def fetch(self, criteria="ALL", **kwargs):
        self.fetch_calls.append({"criteria": str(criteria), **kwargs})
        if "UID " in str(criteria):
            uid = str(criteria).split("UID ", 1)[1].rstrip(")")
            return iter([message for message in self.messages if str(message.uid) == uid])
        return iter(self.messages)


@contextmanager
def _mailbox_context(mailbox):
    yield mailbox


class _GmailImportServiceCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.gmail_config = GmailAccessAccount.objects.create(
            name="Primary Gmail Access Account",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )


class GmailImportServiceTest(_GmailImportServiceCase):
    def test_list_recent_sent_messages_returns_recent_sent_summaries(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="123",
                    subject="Recent Campaign",
                    date=datetime(2026, 4, 6, 9, 0),
                    html="<html><body><p>Hello from Gmail</p></body></html>",
                    text="Hello from Gmail",
                )
            ]
        )

        with patch("apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            messages = list_recent_sent_messages(limit=5)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_id"], "123")
        self.assertEqual(messages[0]["subject"], "Recent Campaign")
        self.assertEqual(messages[0]["snippet"], "Hello from Gmail")
        self.assertTrue(messages[0]["has_html"])
        self.assertEqual(
            mailbox.fetch_calls[0],
            # Credential mail (tagged X-I2G-Mail-Class: credential) is left out of the search.
            {"criteria": UNTAGGED, "limit": 5, "reverse": True, "mark_seen": False, "bulk": True},
        )

    def test_list_recent_sent_messages_uses_requested_mailbox(self):
        mailbox = _FakeMailbox([])

        with patch(
            "apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)
        ) as mock_open:
            list_recent_sent_messages(limit=5, mailbox="shared@ucmerced.edu")

        mock_open.assert_called_once_with(mailbox="shared@ucmerced.edu")

    def test_fetch_message_html_fragment_extracts_body_from_full_document(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="1001",
                    subject="Subject",
                    date=datetime(2026, 4, 6, 9, 0),
                    html="<html><head><title>T</title></head><body><p>Hello <strong>world</strong></p></body></html>",
                    text="Hello world",
                )
            ]
        )

        with patch("apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            fragment = fetch_message_html_fragment("1001")

        self.assertEqual(fragment, "<p>Hello <strong>world</strong></p>")
        self.assertEqual(
            mailbox.fetch_calls[0],
            {"criteria": f"({UNTAGGED} UID 1001)", "limit": 1, "mark_seen": False, "bulk": False},
        )

    def test_fetch_message_html_fragment_uses_requested_mailbox(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="1001",
                    subject="Subject",
                    date=datetime(2026, 4, 6, 9, 0),
                    html="<p>Hello</p>",
                    text="Hello",
                )
            ]
        )

        with patch(
            "apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)
        ) as mock_open:
            fetch_message_html_fragment("1001", mailbox="shared@ucmerced.edu")

        mock_open.assert_called_once_with(mailbox="shared@ucmerced.edu")

    def test_fetch_message_html_fragment_replaces_magic_login_token_links(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="1001",
                    subject="Subject",
                    date=datetime(2026, 4, 6, 9, 0),
                    html=(
                        '<html><body><a href="https://example.test/magic-login?token=victim-token&next=/portal">'
                        "Log in</a></body></html>"
                    ),
                    text="Log in",
                )
            ]
        )

        with patch("apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            fragment = fetch_message_html_fragment("1001")

        self.assertIn("{{ login_link }}", fragment)
        self.assertNotIn("victim-token", fragment)
        self.assertNotIn("/magic-login?token=", fragment)

    def test_fetch_message_html_fragment_replaces_login_link_token_links(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="1001",
                    subject="Subject",
                    date=datetime(2026, 4, 6, 9, 0),
                    html=(
                        '<html><body><a href="https://example.test/login-link?token=victim-token">'
                        "Log in</a> or /login-link?token=victim-token</body></html>"
                    ),
                    text="Log in",
                )
            ]
        )

        with patch("apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            fragment = fetch_message_html_fragment("1001")

        self.assertIn("{{ login_link }}", fragment)
        self.assertNotIn("victim-token", fragment)
        self.assertNotIn("/login-link?token=", fragment)
