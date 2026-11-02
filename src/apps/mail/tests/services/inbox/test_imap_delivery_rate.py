"""Gmail IMAP sessions under the delivery-rate limiter: each uncached read is one ``gmail_imap`` session, Gmail's
answers pause or stop the account, a stopped account is never connected to, and the inbox shows the last list read
with a banner while reads are held back."""

import imaplib
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from imap_tools.errors import MailboxLoginError

from apps.core.models import DeliveryRateState, GmailAccessAccount
from apps.core.services.delivery_rates.runtime import feedback
from apps.core.tests.services.delivery_rates.helpers import FakeClock
from apps.event.tests.helpers import make_superuser
from apps.mail.services.gmail_import import GmailImportBusy, GmailImportError, list_recent_sent_messages
from apps.mail.services.inbox import InboxBusy, InboxError, list_inbox_messages

INBOX_MAILBOX = "apps.mail.services.inbox.connection.MailBox"
IMPORT_MAILBOX = "apps.mail.services.gmail_import.MailBox"
IDENTITY = "imap.gmail.com:i2g@example.edu"


def message(uid="7", subject="Hello"):
    item = MagicMock(uid=uid, subject=subject, flags=(), date=None, html="", text="Body", headers={})
    item.from_values = MagicMock(name="Alice", email="alice@example.com")
    item.to_values = []
    return item


def mailbox_factory(*, messages=(), login_result=("OK", [b"authenticated (Success)"]), login_error=None):
    """A stand-in for ``imap_tools.MailBox``: ``MailBox(host, timeout=...).login(...)`` as a context manager."""
    factory = MagicMock()
    client = factory.return_value.login.return_value.__enter__.return_value
    client.login_result = login_result
    client.fetch.return_value = list(messages)
    if login_error is not None:
        factory.return_value.login.side_effect = login_error
    return factory


def refused(text: bytes):
    return MailboxLoginError(command_result=("NO", [text]), expected="OK")


class GmailImapRateTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)
        self.account = GmailAccessAccount.objects.create(
            name="Gmail",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="i2g@example.edu",
            gmail_password="app-password",
        )

    def state(self):
        return DeliveryRateState.objects.get(channel="gmail_imap", identity=IDENTITY)

    def list_now(self):
        return list_inbox_messages(limit=15, force_refresh=True)


class ImapSessionTests(GmailImapRateTestCase):
    def test_each_session_is_admitted_on_the_account_with_the_settings_timeout(self):
        factory = mailbox_factory(messages=[message()])

        with patch(INBOX_MAILBOX, factory):
            self.assertEqual([item["uid"] for item in self.list_now()], ["7"])

        factory.assert_called_once_with("imap.gmail.com", timeout=30)
        state = self.state()
        self.assertEqual((state.cooldown_group, state.last_signal), ("gmail:i2g@example.edu", "ok"))

    def test_a_bandwidth_suspension_means_no_connection_for_the_breaker_window(self):
        overquota = imaplib.IMAP4.abort("[OVERQUOTA] Account exceeded command or bandwidth limits.")
        with patch(INBOX_MAILBOX, mailbox_factory(login_error=overquota)), self.assertRaises(InboxError):
            self.list_now()
        suspended_at = self.clock.now()

        factory = mailbox_factory(messages=[message()])
        with patch(INBOX_MAILBOX, factory):
            for elapsed in (0, 1_800, 3_590):  # channels.gmail_imap.bandwidth_breaker_seconds is 3,600
                self.clock.current = suspended_at + timedelta(seconds=elapsed)
                with self.subTest(elapsed=elapsed), self.assertRaises(InboxBusy):
                    self.list_now()
            factory.assert_not_called()

            self.clock.current = suspended_at + timedelta(seconds=3_600)
            self.assertEqual(len(self.list_now()), 1)  # the breaker's probe: one session, which closes it
        factory.assert_called_once()
        self.assertEqual(self.state().breaker_state, "closed")

    def test_too_many_connections_pauses_reads_for_the_settings_pause(self):
        busy = refused(b"[ALERT] Too many simultaneous connections. (Failure)")
        with patch(INBOX_MAILBOX, mailbox_factory(login_error=busy)), self.assertRaises(InboxError):
            self.list_now()

        with patch(INBOX_MAILBOX, mailbox_factory()) as factory, self.assertRaises(InboxBusy) as caught:
            self.list_now()

        factory.assert_not_called()
        self.assertEqual(caught.exception.retry_after, 60)
        self.assertEqual(str(caught.exception), "Gmail is busy; try again in about 60 seconds.")

    def test_a_login_gmail_marks_throttled_still_reads_but_slows_down(self):
        throttled = ("OK", [b"[THROTTLED] i2g@example.edu authenticated (Success)"])

        with patch(INBOX_MAILBOX, mailbox_factory(messages=[message()], login_result=throttled)):
            self.assertEqual(len(self.list_now()), 1)

        state = self.state()
        self.assertEqual(state.last_signal, "throttle")
        self.assertIsNotNone(state.cooldown_until)

    def test_refused_credentials_stop_reads_until_the_account_is_saved(self):
        with (
            patch(INBOX_MAILBOX, mailbox_factory(login_error=refused(b"[AUTHENTICATIONFAILED] Invalid credentials"))),
            self.assertRaises(InboxError),
        ):
            self.list_now()
        with patch(INBOX_MAILBOX, mailbox_factory()) as factory, self.assertRaises(InboxBusy) as caught:
            self.list_now()
        factory.assert_not_called()
        self.assertIn("refused the sign-in", str(caught.exception))

        with self.captureOnCommitCallbacks(execute=True):
            self.account.gmail_password = "new-app-password"
            self.account.save()

        with patch(INBOX_MAILBOX, mailbox_factory(messages=[message()])) as factory:
            self.assertEqual(len(self.list_now()), 1)
        factory.assert_called_once()

    def test_a_cache_hit_never_takes_a_slot(self):
        with (
            patch(INBOX_MAILBOX, mailbox_factory(messages=[message()])),
            patch.object(feedback, "admit", wraps=feedback.admit) as admit,
        ):
            list_inbox_messages(limit=15)
            list_inbox_messages(limit=15)

        admit.assert_called_once()

    def test_a_missing_message_is_the_sites_answer_not_gmails(self):
        from apps.mail.services.inbox import fetch_inbox_message

        with patch(INBOX_MAILBOX, mailbox_factory()), self.assertRaisesMessage(InboxError, "Message not found."):
            fetch_inbox_message("99")

        self.assertEqual(self.state().last_signal, "ok")


class GmailImportRateTests(GmailImapRateTestCase):
    def test_a_held_back_import_says_when_to_try_again_without_connecting(self):
        overquota = imaplib.IMAP4.abort("[OVERQUOTA] Account exceeded command or bandwidth limits.")
        with patch(IMPORT_MAILBOX, mailbox_factory(login_error=overquota)), self.assertRaises(GmailImportError):
            list_recent_sent_messages(limit=5, force_refresh=True)

        with patch(IMPORT_MAILBOX, mailbox_factory()) as factory, self.assertRaises(GmailImportBusy) as caught:
            list_recent_sent_messages(limit=5, force_refresh=True)

        factory.assert_not_called()
        self.assertIn("Gmail is busy; try again in about", str(caught.exception))


class InboxBannerTests(GmailImapRateTestCase):
    def setUp(self):
        super().setUp()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.url = reverse("admin:mail_inbox_fragment")

    def hold_back_reads(self):
        busy = refused(b"[ALERT] Too many simultaneous connections. (Failure)")
        with patch(INBOX_MAILBOX, mailbox_factory(login_error=busy)), self.assertRaises(InboxError):
            self.list_now()

    def test_while_reads_are_held_back_the_last_list_read_is_shown_with_a_banner(self):
        with patch(INBOX_MAILBOX, mailbox_factory(messages=[message(subject="Last seen subject")])):
            self.client.get(self.url, {"limit": 15, "refresh": "1"})
        self.hold_back_reads()

        response = self.client.get(self.url, {"limit": 15, "refresh": "1"})

        self.assertContains(response, "data-inbox-busy")
        self.assertContains(response, "Gmail is busy; try again in about")
        self.assertContains(response, "Showing the messages as last loaded.")
        self.assertContains(response, "Last seen subject")

    def test_without_a_list_read_before_only_the_banner_is_shown(self):
        self.hold_back_reads()

        response = self.client.get(self.url, {"limit": 15, "refresh": "1"})

        self.assertContains(response, "Gmail is busy; try again in about")
        self.assertNotContains(response, "Showing the messages as last loaded.")
        self.assertNotContains(response, "No messages in")
