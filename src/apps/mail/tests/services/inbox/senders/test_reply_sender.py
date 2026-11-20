"""``send_reply(sender=...)``: a reply goes out From the chosen sending address, and only a listed one."""

from unittest.mock import patch

from django.test import TestCase

from apps.core.models import EmailServiceConfig, GmailAccessAccount
from apps.mail.services.inbox.reply import (
    REPLY_DELIVERY_NOT_CONFIGURED,
    REPLY_INVALID_ADDRESS_MESSAGE,
    REPLY_SEND_FAILURE_MESSAGE,
    REPLY_SENDER_UNAVAILABLE_MESSAGE,
    send_reply,
)
from apps.mail.services.inbox.senders import resolve_identity
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_backend import MAILBOX, graph_config
from apps.mail.tests.services.inbox.senders.test_send_identities import SenderFixtureMixin

DELIVER = "apps.mail.services.inbox.reply.deliver_email"


def reply(**overrides):
    values = {"to_email": "alice@example.com", "subject": "Re: Hi", "reply_body": "Hello"}
    return send_reply(**{**values, **overrides})


class ReplySenderTests(SenderFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.email_config = self.default_sender()

    @patch(DELIVER)
    def test_the_default_sender_uses_notification_delivery(self, deliver):
        for sender in ("default", ""):
            with self.subTest(sender=sender):
                deliver.reset_mock()

                self.assertEqual(reply(sender=sender), "")

                self.assertEqual(deliver.call_args.kwargs["config"], self.email_config)

    @patch(DELIVER)
    def test_an_unlisted_sender_is_refused_and_nothing_is_sent(self, deliver):
        for sender in ("graph:nobody@contoso.com", "imap:999999", "bogus"):
            with self.subTest(sender=sender):
                self.assertEqual(reply(sender=sender), REPLY_SENDER_UNAVAILABLE_MESSAGE)

        deliver.assert_not_called()

    @patch(DELIVER)
    def test_a_graph_sender_sends_through_graph_from_its_mailbox(self, deliver):
        graph_config()

        self.assertEqual(reply(sender=f"graph:{MAILBOX}"), "")

        config = deliver.call_args.kwargs["config"]
        self.assertEqual((config.provider, config.from_email, config.from_name), ("graph", MAILBOX, "I2G"))
        self.assertTrue(config.is_active)

    @patch(DELIVER)
    def test_an_imap_sender_sends_over_its_own_smtp_login(self, deliver):
        row = self.reply_account()

        self.assertEqual(reply(sender=f"imap:{row.pk}"), "")

        config = deliver.call_args.kwargs["config"]
        self.assertEqual(
            (config.provider, config.from_email, config.gmail_account_id), ("gmail_smtp", "reply@gmail.com", row.pk)
        )
        message = deliver.call_args.args[0]
        self.assertEqual(message.to, ("alice@example.com",))

    @patch(DELIVER)
    def test_another_sender_does_not_need_notification_delivery(self, deliver):
        EmailServiceConfig.objects.update(provider="smtp")  # no SMTP provider configured: the default cannot send
        row = self.reply_account()

        self.assertEqual(reply(sender="default"), REPLY_DELIVERY_NOT_CONFIGURED)
        self.assertEqual(reply(sender=f"imap:{row.pk}"), "")
        deliver.assert_called_once()

    @patch(DELIVER)
    def test_invalid_recipients_are_refused_before_the_sender_is_checked(self, deliver):
        self.assertEqual(reply(sender="bogus", to_email="not an address"), REPLY_INVALID_ADDRESS_MESSAGE)
        deliver.assert_not_called()


class ImapReplyEndToEndTests(SenderFixtureMixin, TestCase):
    """Through the real facade and the ``gmail_smtp`` provider, down to a patched ``smtplib.SMTP``."""

    @patch("apps.core.services.email.smtp.ssl.create_default_context")
    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_the_reply_is_sent_with_the_account_login(self, smtp_class, _context):
        smtp_class.return_value.send_message.return_value = {}
        row = self.reply_account(gmail_password="app-password-2", smtp_port=2525)

        self.assertEqual(reply(sender=f"imap:{row.pk}", cc_email="cc@example.com"), "")

        self.assertEqual(smtp_class.call_args.args, ("smtp.gmail.com", 2525))
        client = smtp_class.return_value
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("reply@gmail.com", "app-password-2")
        kwargs = client.send_message.call_args.kwargs
        self.assertEqual(kwargs["from_addr"], "reply@gmail.com")
        self.assertEqual(kwargs["to_addrs"], ["alice@example.com", "cc@example.com"])
        self.assertIn("reply@gmail.com", client.send_message.call_args.args[0]["From"])

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_replies_turned_off_meanwhile_are_not_sent(self, smtp_class):
        row = self.reply_account()
        identity = resolve_identity(f"imap:{row.pk}")
        # The sender was resolved while the account allowed replies; they are turned off before the provider is
        # built, and the ``gmail_smtp`` factory re-checks the row.
        GmailAccessAccount.objects.filter(pk=row.pk).update(reply_enabled=False)

        with (
            patch("apps.mail.services.inbox.reply.resolve_identity", return_value=identity),
            self.assertLogs("apps.mail.services.inbox.reply", "ERROR"),
        ):
            error = reply(sender=f"imap:{row.pk}")

        self.assertEqual(error, REPLY_SEND_FAILURE_MESSAGE)
        smtp_class.assert_not_called()
