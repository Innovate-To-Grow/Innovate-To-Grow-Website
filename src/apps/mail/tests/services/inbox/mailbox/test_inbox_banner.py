from unittest.mock import patch

from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.services.inbox import InboxError
from apps.mail.tests.services.inbox.gmail_import.test_imap_delivery_rate import (
    INBOX_MAILBOX,
    GmailImapRateTestCase,
    mailbox_factory,
    message,
    refused,
)


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
