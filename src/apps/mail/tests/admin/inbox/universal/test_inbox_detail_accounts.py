"""The universal inbox detail views read the account named by ``?account=`` and reply in it."""

from django.urls import reverse

from apps.mail.tests.admin.inbox.universal.helpers import (
    UniversalInboxViewCase,
    detail,
)


class InboxDetailAccountTests(UniversalInboxViewCase):
    def setUp(self):
        super().setUp()
        self.fetch = self.patch("fetch_inbox_message", return_value=detail())

    def test_the_detail_page_reads_the_named_account_and_replies_in_it(self):
        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]) + "?account=imap:7")

        self.fetch.assert_called_once_with("42", folder="INBOX", account="imap:7")
        self.assertContains(response, reverse("admin:mail_inbox_reply", args=["42"]) + "?account=imap%3A7")

    def test_the_detail_fragment_reads_the_named_account_and_replies_in_it(self):
        response = self.client.get(
            reverse("admin:mail_inbox_detail_fragment", args=["42"]) + "?folder=INBOX&account=imap:7"
        )

        self.fetch.assert_called_once_with("42", folder="INBOX", account="imap:7")
        self.assertContains(response, reverse("admin:mail_inbox_reply_fragment", args=["42"]) + "?account=imap%3A7")

    def test_without_an_account_the_urls_carry_none(self):
        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.fetch.assert_called_once_with("42", folder="INBOX", account="")
        self.assertNotContains(response, "?account=")
