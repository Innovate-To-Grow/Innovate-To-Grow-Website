from types import SimpleNamespace
from unittest.mock import Mock, patch

from apps.mail.services.campaign.gmail_import import DEFAULT_GMAIL_FOLDER, GmailImportError
from apps.mail.tests.services.inbox.gmail_import.test_gmail_import import _GmailImportServiceCase


class GmailImportServiceTest(_GmailImportServiceCase):
    def test_open_mailbox_reraises_gmail_import_error(self):
        from apps.mail.services.campaign.gmail_import.connection import _open_mailbox

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
            patch("apps.mail.services.campaign.gmail_import.GmailAccessAccount.load", return_value=config),
            patch("apps.mail.services.campaign.gmail_import.MailBox", return_value=mailbox_client),
            patch(
                "apps.mail.services.campaign.gmail_import.connection.select_sent_folder",
                side_effect=GmailImportError("no sent folder"),
            ),
        ):
            with self.assertRaisesMessage(GmailImportError, "no sent folder"):
                with _open_mailbox():
                    pass

    def test_iter_sent_folder_candidates_includes_sent_flagged_folders(self):
        from apps.mail.services.campaign.gmail_import.connection import iter_sent_folder_candidates

        client = Mock()
        client.folder.list.return_value = [
            SimpleNamespace(name="Custom Sent", flags=("\\Sent",)),
            SimpleNamespace(name="Inbox", flags=("\\Inbox",)),
        ]

        candidates = iter_sent_folder_candidates(client)

        self.assertIn("Custom Sent", candidates)
        self.assertNotIn("Inbox", candidates)

    def test_iter_sent_folder_candidates_handles_listing_failure(self):
        from apps.mail.services.campaign.gmail_import.connection import (
            SENT_FOLDER_CANDIDATES,
            iter_sent_folder_candidates,
        )

        client = Mock()
        client.folder.list.side_effect = RuntimeError("imap error")

        candidates = iter_sent_folder_candidates(client)

        # Falls back to the static candidate list when listing fails.
        self.assertEqual(candidates, SENT_FOLDER_CANDIDATES)

    def test_select_sent_folder_raises_when_no_candidate_opens(self):
        from apps.mail.services.campaign.gmail_import.connection import select_sent_folder

        client = Mock()
        client.folder.list.return_value = []
        client.folder.set.side_effect = RuntimeError("cannot open")

        with self.assertRaisesMessage(GmailImportError, "Unable to open the sent-mail folder"):
            select_sent_folder(client)

    def test_list_recent_sent_messages_returns_cached(self):
        from django.core.cache import cache as dj_cache

        from apps.mail.services.campaign.gmail_import.messages import list_recent_sent_messages

        cached = [{"message_id": "1", "subject": "cached"}]
        with patch(
            "apps.mail.services.campaign.gmail_import.messages.resolve_gmail_mailbox", return_value="m@example.com"
        ):
            dj_cache.set("gmail_import:list:m@example.com:5", cached, 300)
            result = list_recent_sent_messages(limit=5)

        self.assertEqual(result, cached)

    def test_fetch_message_html_fragment_returns_cached(self):
        from django.core.cache import cache as dj_cache

        from apps.mail.services.campaign.gmail_import.messages import fetch_message_html_fragment

        with patch(
            "apps.mail.services.campaign.gmail_import.messages.resolve_gmail_mailbox", return_value="m@example.com"
        ):
            dj_cache.set("gmail_import:msg:m@example.com:msg-1", "<p>cached</p>", 1800)
            result = fetch_message_html_fragment("msg-1")

        self.assertEqual(result, "<p>cached</p>")

    def test_format_sent_at_with_string_and_empty(self):
        from apps.mail.services.campaign.gmail_import.messages import format_sent_at

        self.assertEqual(format_sent_at("Mon 1 Jan"), "Mon 1 Jan")
        self.assertEqual(format_sent_at(None), "")

    def test_build_snippet_returns_empty_when_no_body(self):
        from apps.mail.services.campaign.gmail_import.messages import build_snippet

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
            patch("apps.mail.services.campaign.gmail_import.GmailAccessAccount.load", return_value=config),
            patch("apps.mail.services.campaign.gmail_import.MailBox", return_value=mailbox_client) as mock_mailbox,
        ):
            from apps.mail.services.campaign.gmail_import import _open_mailbox

            with _open_mailbox(mailbox="shared@ucmerced.edu") as client:
                self.assertIs(client, login_client)

        # Each session connects with the gmail_imap channel's timeout (DELIVERY_RATES).
        mock_mailbox.assert_called_once_with("imap.gmail.com", timeout=30)
        mailbox_client.login.assert_called_once_with("shared@ucmerced.edu", "app-password", initial_folder=None)
        login_client.folder.set.assert_any_call(DEFAULT_GMAIL_FOLDER)
        login_client.folder.set.assert_any_call("Sent Mail")
