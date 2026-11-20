"""Inbox replies: rendering the reply body and threading headers, and sending it."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.email import PermanentEmailDeliveryError
from apps.mail.services.inbox.sending.reply import (
    REPLY_SEND_FAILURE_MESSAGE,
    _build_reply_message,
    render_reply_html,
    send_reply,
)


class ReplyRenderTests(TestCase):
    def test_render_reply_html_linkifies_urls(self):
        html = render_reply_html("Visit https://example.com now", quoted_text="prior text")
        self.assertIn('<a href="https://example.com"', html)
        self.assertIn("prior text", html)

    def test_build_reply_message_sets_threading_headers(self):
        config = SimpleNamespace(source_address="I2G <reply@example.com>")
        message = _build_reply_message(
            config=config,
            to_email="alice@example.com",
            subject="Re: Hi",
            html="<p>Hi</p>",
            cc_list=["cc@example.com"],
            in_reply_to="<orig@example.com>",
            references="<a@example.com> <b@example.com>",
        )

        self.assertEqual(message.headers["In-Reply-To"], "<orig@example.com>")
        self.assertEqual(message.headers["References"], "<a@example.com> <b@example.com>")
        self.assertEqual(message.cc, ("cc@example.com",))


class SendReplyTests(TestCase):
    def setUp(self):
        self.email_config = EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            from_email="reply@example.com",
            from_name="I2G",
        )

    def test_send_reply_returns_empty_on_success(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch("apps.mail.services.inbox.sending.reply.deliver_email") as mock_deliver:
            error = send_reply(
                to_email="alice@example.com",
                subject="Re: Hi",
                reply_body="Hello",
                cc_email="cc@example.com",
            )

        self.assertEqual(error, "")
        mock_deliver.assert_called_once()
        message = mock_deliver.call_args.args[0]
        self.assertEqual(message.envelope_recipients, ("alice@example.com", "cc@example.com"))

    def test_send_reply_returns_message_when_aws_credentials_missing(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch(
            "apps.mail.services.inbox.sending.reply.deliver_email", side_effect=PermanentEmailDeliveryError("missing")
        ):
            error = send_reply(to_email="alice@example.com", subject="Re: Hi", reply_body="Hi")

        self.assertEqual(error, REPLY_SEND_FAILURE_MESSAGE)

    def test_send_reply_returns_failure_message_on_unexpected_error(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch(
            "apps.mail.services.inbox.sending.reply.deliver_email",
            side_effect=PermanentEmailDeliveryError("provider down"),
        ):
            error = send_reply(to_email="alice@example.com", subject="Re: Hi", reply_body="Hi")

        self.assertEqual(error, REPLY_SEND_FAILURE_MESSAGE)
