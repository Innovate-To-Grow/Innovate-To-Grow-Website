from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db.utils import OperationalError
from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.mail.models import EmailCampaign
from apps.mail.services.gmail_import import (
    DEFAULT_GMAIL_FOLDER,
    DEFAULT_GMAIL_MAILBOX,
    GmailImportError,
    fetch_message_html_fragment,
    import_message_into_campaign,
    list_recent_sent_messages,
    resolve_gmail_mailbox,
)
from apps.mail.services.preview import HTML_MARKER, render_preview


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


class GmailImportServiceTest(TestCase):
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
            {"criteria": "ALL", "limit": 5, "reverse": True, "mark_seen": False, "bulk": True},
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
            {"criteria": "(UID 1001)", "limit": 1, "mark_seen": False, "bulk": False},
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

    def test_fetch_message_html_fragment_replaces_cached_magic_login_token_links(self):
        from django.core.cache import cache as dj_cache

        dj_cache.set(
            "gmail_import:msg:campaigns@ucmerced.edu:msg-1",
            '<a href="/magic-login?token=cached-victim-token">Log in</a>',
            1800,
        )

        fragment = fetch_message_html_fragment("msg-1")

        self.assertIn("{{ login_link }}", fragment)
        self.assertNotIn("cached-victim-token", fragment)

    def test_import_message_into_campaign_saves_html_marker(self):
        campaign = EmailCampaign.objects.create(
            subject="Campaign",
            body="Before import",
            login_redirect_path="/account",
        )

        with patch("apps.mail.services.gmail_import.fetch_message_html_fragment", return_value="<p>Imported</p>"):
            import_message_into_campaign(campaign, "msg-1")

        campaign.refresh_from_db()
        self.assertEqual(campaign.body, HTML_MARKER + "<p>Imported</p>")

    def test_import_message_into_campaign_scrubs_magic_login_token_links(self):
        campaign = EmailCampaign.objects.create(
            subject="Campaign",
            body="Before import",
            login_redirect_path="/account",
        )

        with patch(
            "apps.mail.services.gmail_import.fetch_message_html_fragment",
            return_value='<a href="/magic-login?token=victim-token">Log in</a>',
        ):
            import_message_into_campaign(campaign, "msg-1")

        campaign.refresh_from_db()
        self.assertIn("{{ login_link }}", campaign.body)
        self.assertNotIn("victim-token", campaign.body)

    def test_open_mailbox_raises_when_gmail_import_config_missing(self):
        with patch(
            "apps.mail.services.gmail_import.GmailAccessAccount.load",
            return_value=SimpleNamespace(is_configured=False, mailbox="", imap_host="", gmail_username=""),
        ):
            with self.assertRaises(GmailImportError):
                list_recent_sent_messages()

    def test_resolve_gmail_mailbox_raises_friendly_error_when_migration_missing(self):
        with patch(
            "apps.mail.services.gmail_import.GmailAccessAccount.load",
            side_effect=OperationalError("no such table: core_gmailaccessaccount"),
        ):
            with self.assertRaisesMessage(
                GmailImportError,
                "Gmail import configuration is unavailable. Run the latest migrations first.",
            ):
                resolve_gmail_mailbox()

    def test_fetch_message_html_fragment_raises_when_html_missing(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="1001",
                    subject="No HTML",
                    date=datetime(2026, 4, 6, 9, 0),
                    html="",
                    text="Only plain text",
                )
            ]
        )

        with patch("apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            with self.assertRaises(GmailImportError):
                fetch_message_html_fragment("1001")

    def test_fetch_message_html_fragment_raises_when_message_missing(self):
        mailbox = _FakeMailbox([])

        with patch("apps.mail.services.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            with self.assertRaises(GmailImportError):
                fetch_message_html_fragment("9999")

    def test_resolve_gmail_mailbox_uses_active_import_mailbox(self):
        self.assertEqual(resolve_gmail_mailbox(), "campaigns@ucmerced.edu")

    def test_resolve_gmail_mailbox_falls_back_to_default_when_unconfigured(self):
        with patch(
            "apps.mail.services.gmail_import.GmailAccessAccount.load",
            return_value=SimpleNamespace(mailbox=""),
        ):
            mailbox = resolve_gmail_mailbox()

        self.assertEqual(mailbox, DEFAULT_GMAIL_MAILBOX)

    def test_render_preview_wraps_imported_raw_html_without_escaping(self):
        campaign = Mock(subject="Preview", body=HTML_MARKER + "<p><strong>Imported</strong> HTML</p>")

        preview = render_preview(campaign)

        self.assertIn("Innovate to Grow", preview["html"])
        self.assertIn("<strong>Imported</strong>", preview["html"])
        self.assertNotIn("&lt;strong&gt;Imported", preview["html"])

    def test_get_gmail_config_raises_on_db_error(self):
        from apps.mail.services.gmail_import.connection import get_gmail_config

        with patch(
            "apps.mail.services.gmail_import.GmailAccessAccount.load",
            side_effect=OperationalError("no such table"),
        ):
            with self.assertRaisesMessage(GmailImportError, "Gmail import configuration is unavailable"):
                get_gmail_config()

    def test_open_mailbox_reraises_gmail_import_error(self):
        from apps.mail.services.gmail_import.connection import _open_mailbox

        config = SimpleNamespace(
            is_configured=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
            mailbox="campaigns@ucmerced.edu",
        )
        mailbox_client = Mock()
        login_context = Mock()
        login_context.__enter__ = Mock(return_value=Mock())
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.gmail_import.GmailAccessAccount.load", return_value=config),
            patch("apps.mail.services.gmail_import.MailBox", return_value=mailbox_client),
            patch(
                "apps.mail.services.gmail_import.connection.select_sent_folder",
                side_effect=GmailImportError("no sent folder"),
            ),
        ):
            with self.assertRaisesMessage(GmailImportError, "no sent folder"):
                with _open_mailbox():
                    pass

    def test_iter_sent_folder_candidates_includes_sent_flagged_folders(self):
        from apps.mail.services.gmail_import.connection import iter_sent_folder_candidates

        client = Mock()
        client.folder.list.return_value = [
            SimpleNamespace(name="Custom Sent", flags=("\\Sent",)),
            SimpleNamespace(name="Inbox", flags=("\\Inbox",)),
        ]

        candidates = iter_sent_folder_candidates(client)

        self.assertIn("Custom Sent", candidates)
        self.assertNotIn("Inbox", candidates)

    def test_iter_sent_folder_candidates_handles_listing_failure(self):
        from apps.mail.services.gmail_import.connection import SENT_FOLDER_CANDIDATES, iter_sent_folder_candidates

        client = Mock()
        client.folder.list.side_effect = RuntimeError("imap error")

        candidates = iter_sent_folder_candidates(client)

        # Falls back to the static candidate list when listing fails.
        self.assertEqual(candidates, SENT_FOLDER_CANDIDATES)

    def test_select_sent_folder_raises_when_no_candidate_opens(self):
        from apps.mail.services.gmail_import.connection import select_sent_folder

        client = Mock()
        client.folder.list.return_value = []
        client.folder.set.side_effect = RuntimeError("cannot open")

        with self.assertRaisesMessage(GmailImportError, "Unable to open the sent-mail folder"):
            select_sent_folder(client)

    def test_list_recent_sent_messages_returns_cached(self):
        from django.core.cache import cache as dj_cache

        from apps.mail.services.gmail_import.messages import list_recent_sent_messages

        cached = [{"message_id": "1", "subject": "cached"}]
        with patch("apps.mail.services.gmail_import.messages.resolve_gmail_mailbox", return_value="m@example.com"):
            dj_cache.set("gmail_import:list:m@example.com:5", cached, 300)
            result = list_recent_sent_messages(limit=5)

        self.assertEqual(result, cached)

    def test_fetch_message_html_fragment_returns_cached(self):
        from django.core.cache import cache as dj_cache

        from apps.mail.services.gmail_import.messages import fetch_message_html_fragment

        with patch("apps.mail.services.gmail_import.messages.resolve_gmail_mailbox", return_value="m@example.com"):
            dj_cache.set("gmail_import:msg:m@example.com:msg-1", "<p>cached</p>", 1800)
            result = fetch_message_html_fragment("msg-1")

        self.assertEqual(result, "<p>cached</p>")

    def test_format_sent_at_with_string_and_empty(self):
        from apps.mail.services.gmail_import.messages import format_sent_at

        self.assertEqual(format_sent_at("Mon 1 Jan"), "Mon 1 Jan")
        self.assertEqual(format_sent_at(None), "")

    def test_build_snippet_returns_empty_when_no_body(self):
        from apps.mail.services.gmail_import.messages import build_snippet

        self.assertEqual(build_snippet(SimpleNamespace(html="", text="")), "")

    def test_open_mailbox_uses_requested_mailbox_and_auto_detects_sent_folder(self):
        config = SimpleNamespace(
            is_configured=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
            mailbox="campaigns@ucmerced.edu",
        )
        login_client = Mock()
        login_client.folder.list.return_value = [SimpleNamespace(name="[Gmail]/Sent Mail", flags=("\\Sent",))]
        login_client.folder.set.side_effect = [RuntimeError("missing Sent"), RuntimeError("missing Sent Mail"), None]
        login_context = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.gmail_import.GmailAccessAccount.load", return_value=config),
            patch("apps.mail.services.gmail_import.MailBox", return_value=mailbox_client) as mock_mailbox,
        ):
            from apps.mail.services.gmail_import import _open_mailbox

            with _open_mailbox(mailbox="shared@ucmerced.edu") as client:
                self.assertIs(client, login_client)

        mock_mailbox.assert_called_once_with("imap.gmail.com")
        mailbox_client.login.assert_called_once_with("shared@ucmerced.edu", "app-password", initial_folder=None)
        login_client.folder.set.assert_any_call(DEFAULT_GMAIL_FOLDER)
        login_client.folder.set.assert_any_call("Sent Mail")
