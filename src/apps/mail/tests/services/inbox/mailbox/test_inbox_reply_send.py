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

DOCS = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit?usp=sharing"


def anchor(href: str) -> str:
    return f'<a href="{href}" style="color:#0f2d52;">{href}</a>'


class ReplyRenderTests(TestCase):
    def test_render_reply_html_linkifies_urls(self):
        html = render_reply_html("Visit https://example.com now", quoted_text="prior text")
        self.assertIn('<a href="https://example.com"', html)
        self.assertIn("prior text", html)

    def test_a_link_is_found_in_the_text_as_written_and_ends_where_the_sentence_goes_on(self):
        # Found in the escaped text, a link ended at its first "&" and took the punctuation and words after it.
        cases = (
            (
                f"Edit {DOCS}&tab=t.0#heading=h.abc123 (edit it)",
                f"Edit {anchor(f'{DOCS}&amp;tab=t.0#heading=h.abc123')} (edit it)",
            ),
            (f"Row: {DOCS},[sign-in link removed],team B", f"Row: {anchor(DOCS)},[sign-in link removed],team B"),
            (f"Open {DOCS}. Then (see {DOCS}).", f"Open {anchor(DOCS)}. Then (see {anchor(DOCS)})."),
            (f"请看{DOCS}谢谢", f"请看{anchor(DOCS)}谢谢"),  # glued to Chinese text
            (
                "Wiki https://en.wikipedia.org/wiki/Mesa_(computing)!",
                f"Wiki {anchor('https://en.wikipedia.org/wiki/Mesa_(computing)')}!",
            ),
        )
        for body, expected in cases:
            with self.subTest(body):
                self.assertIn(expected, render_reply_html(body))

    def test_the_text_around_a_link_is_escaped(self):
        html = render_reply_html('<b>Hi</b> & "you" https://example.org/a?b=1&c=<2>')

        self.assertIn(
            f"&lt;b&gt;Hi&lt;/b&gt; &amp; &quot;you&quot; {anchor('https://example.org/a?b=1&amp;c=')}&lt;2&gt;", html
        )

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
