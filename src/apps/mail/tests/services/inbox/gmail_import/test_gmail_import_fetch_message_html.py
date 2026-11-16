from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db.utils import OperationalError

from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.content.preview import HTML_MARKER, render_preview
from apps.mail.services.campaign.gmail_import import (
    DEFAULT_GMAIL_MAILBOX,
    GmailImportError,
    fetch_message_html_fragment,
    import_message_into_campaign,
    list_recent_sent_messages,
    resolve_gmail_mailbox,
)
from apps.mail.tests.services.inbox.gmail_import.test_gmail_import import (
    _FakeMailbox,
    _GmailImportServiceCase,
    _mailbox_context,
)


class GmailImportServiceTest(_GmailImportServiceCase):
    def test_fetch_message_html_fragment_replaces_fragment_login_tokens(self):
        mailbox = _FakeMailbox(
            [
                SimpleNamespace(
                    uid="1001",
                    subject="Subject",
                    date=datetime(2026, 4, 6, 9, 0),
                    html=(
                        '<html><body><a href="https://example.test/login-link#token=victim-token">'
                        "Log in</a></body></html>"
                    ),
                    text="Log in",
                )
            ]
        )

        with patch("apps.mail.services.campaign.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            fragment = fetch_message_html_fragment("1001")

        self.assertIn("{{ login_link }}", fragment)
        self.assertNotIn("victim-token", fragment)
        self.assertNotIn("/login-link#token=", fragment)

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

        with patch(
            "apps.mail.services.campaign.gmail_import.fetch_message_html_fragment", return_value="<p>Imported</p>"
        ):
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
            "apps.mail.services.campaign.gmail_import.fetch_message_html_fragment",
            return_value='<a href="/magic-login?token=victim-token">Log in</a>',
        ):
            import_message_into_campaign(campaign, "msg-1")

        campaign.refresh_from_db()
        self.assertIn("{{ login_link }}", campaign.body)
        self.assertNotIn("victim-token", campaign.body)

    def test_open_mailbox_raises_when_gmail_import_config_missing(self):
        with patch(
            "apps.mail.services.campaign.gmail_import.GmailAccessAccount.load",
            return_value=SimpleNamespace(is_configured=False, mailbox="", imap_host="", gmail_username=""),
        ):
            with self.assertRaises(GmailImportError):
                list_recent_sent_messages()

    def test_resolve_gmail_mailbox_raises_friendly_error_when_migration_missing(self):
        with patch(
            "apps.mail.services.campaign.gmail_import.GmailAccessAccount.load",
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

        with patch("apps.mail.services.campaign.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            with self.assertRaises(GmailImportError):
                fetch_message_html_fragment("1001")

    def test_fetch_message_html_fragment_raises_when_message_missing(self):
        mailbox = _FakeMailbox([])

        with patch("apps.mail.services.campaign.gmail_import._open_mailbox", return_value=_mailbox_context(mailbox)):
            with self.assertRaises(GmailImportError):
                fetch_message_html_fragment("9999")

    def test_resolve_gmail_mailbox_uses_active_import_mailbox(self):
        self.assertEqual(resolve_gmail_mailbox(), "campaigns@ucmerced.edu")

    def test_resolve_gmail_mailbox_falls_back_to_default_when_unconfigured(self):
        with patch(
            "apps.mail.services.campaign.gmail_import.GmailAccessAccount.load",
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
        from apps.mail.services.campaign.gmail_import.connection import get_gmail_config

        with patch(
            "apps.mail.services.campaign.gmail_import.GmailAccessAccount.load",
            side_effect=OperationalError("no such table"),
        ):
            with self.assertRaisesMessage(GmailImportError, "Gmail import configuration is unavailable"):
                get_gmail_config()
