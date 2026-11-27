"""Gmail keeps a Sent copy of everything it sends, credential mail included: the admin inbox's Sent view and the Gmail
import never list, open, snippet or cache a message tagged ``X-I2G-Mail-Class: credential``. The tag is not
authenticated, so received mail carrying it is still listed."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from imap_tools import MailMessage

from apps.core.models import GmailAccessAccount
from apps.core.tests.services.delivery_rates.helpers import FakeClock
from apps.mail.services.campaign.gmail_import import (
    GmailImportError,
    fetch_message_html_fragment,
    list_recent_sent_messages,
)
from apps.mail.services.campaign.gmail_import.credential_mail import (
    WITHOUT_CREDENTIAL_MAIL,
    is_credential_mail,
)
from apps.mail.services.inbox import InboxError, fetch_inbox_message, list_inbox_messages
from apps.mail.tests.services.inbox.gmail_import.test_imap_delivery_rate import (
    IMPORT_MAILBOX,
    INBOX_MAILBOX,
    mailbox_factory,
    message,
)

CODE = "482913"


def tagged(uid="9"):
    item = message(uid=uid, subject=f"Your sign-in code is {CODE}")
    item.headers = {"x-i2g-mail-class": ("credential",)}
    item.html = f"<p>Code {CODE}</p>"
    item.text = f"Code {CODE}"
    return item


class CredentialCopyTestCase(TestCase):
    def setUp(self):
        cache.clear()
        FakeClock().install(self)
        GmailAccessAccount.objects.create(
            name="Gmail",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="i2g@example.edu",
            gmail_password="app-password",
        )

    def client_of(self, factory):
        return factory.return_value.login.return_value.__enter__.return_value


class InboxFilterTests(CredentialCopyTestCase):
    def test_the_list_search_leaves_tagged_mail_out_and_drops_any_that_comes_back(self):
        factory = mailbox_factory(messages=[message(uid="7"), tagged()])
        with patch(INBOX_MAILBOX, factory):
            rows = list_inbox_messages(limit=15, folder="SENT", force_refresh=True)
        self.assertEqual([row["uid"] for row in rows], ["7"])
        self.assertEqual(self.client_of(factory).uids.call_args.args[0], WITHOUT_CREDENTIAL_MAIL)
        self.assertNotIn(CODE, repr(cache.get("inbox:list:SENT:15")))

    def test_a_tagged_message_is_never_opened_or_cached(self):
        factory = mailbox_factory(messages=[tagged()])
        with patch(INBOX_MAILBOX, factory), self.assertRaises(InboxError):
            fetch_inbox_message("9", folder="SENT")
        self.assertIsNone(cache.get("inbox:msg:SENT:9"))
        self.assertIn("NOT (HEADER", str(self.client_of(factory).fetch.call_args.args[0]))

    def test_received_mail_with_the_tag_is_still_listed_and_opened(self):
        # Anyone can put the header on mail they send the account; honouring it outside Sent would let them hide
        # their message from staff.
        spoofed = tagged(uid="8")
        factory = mailbox_factory(messages=[message(uid="7"), spoofed])
        with patch(INBOX_MAILBOX, factory):
            rows = list_inbox_messages(limit=15, folder="INBOX", force_refresh=True)
        self.assertEqual([row["uid"] for row in rows], ["8", "7"])  # newest UID first
        self.assertEqual(self.client_of(factory).uids.call_args.args[0], "ALL")

        with patch(INBOX_MAILBOX, mailbox_factory(messages=[spoofed])) as factory:
            detail = fetch_inbox_message("8", folder="INBOX")
        self.assertEqual(detail["uid"], "8")
        self.assertNotIn("HEADER", str(self.client_of(factory).fetch.call_args.args[0]))


class ImportFilterTests(CredentialCopyTestCase):
    def test_import_lists_no_tagged_message_and_caches_none(self):
        factory = mailbox_factory(messages=[tagged(), message(uid="7", subject="Newsletter")])
        with patch(IMPORT_MAILBOX, factory):
            rows = list_recent_sent_messages(limit=5, force_refresh=True)
        self.assertEqual([row["message_id"] for row in rows], ["7"])
        self.assertEqual(self.client_of(factory).fetch.call_args.args[0], WITHOUT_CREDENTIAL_MAIL)
        self.assertNotIn(CODE, repr(cache.get("gmail_import:list:i2g@example.edu:5")))

    def test_import_refuses_a_tagged_message(self):
        with patch(IMPORT_MAILBOX, mailbox_factory(messages=[tagged()])), self.assertRaises(GmailImportError):
            fetch_message_html_fragment("9", use_cache=False)
        self.assertIsNone(cache.get("gmail_import:msg:i2g@example.edu:9"))

    def test_only_the_exact_tag_counts(self):
        other = message()
        other.headers = {"x-i2g-mail-class": ("newsletter",)}
        self.assertFalse(is_credential_mail(other))
        self.assertFalse(is_credential_mail(object()))
        self.assertTrue(is_credential_mail(tagged()))

    def test_a_real_imap_tools_message_is_recognised(self):
        # imap_tools gives headers as a LazyHeaders mapping, not a dict: the filter must still see the tag.
        raw = b"X-I2G-Mail-Class: credential\r\nSubject: Your code\r\n\r\nCode " + CODE.encode()

        self.assertTrue(is_credential_mail(MailMessage.from_bytes(raw)))
        self.assertFalse(is_credential_mail(MailMessage.from_bytes(b"Subject: Hello\r\n\r\nHi")))
