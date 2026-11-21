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

    def test_a_closing_quote_backtick_or_emphasis_mark_after_a_link_stays_text(self):
        # The link took the mark closing the quote or emphasis around it, so its href named a page that is not there.
        wiki, drive = "https://en.wikipedia.org/wiki/Merced_(river)", "https://drive.google.com/open?id=1AbC_"
        cases = (
            (f"He wrote '{DOCS}' in his note", f"He wrote &#x27;{anchor(DOCS)}&#x27; in his note"),
            ("see 'https://x.example/s'.", f"see &#x27;{anchor('https://x.example/s')}&#x27;."),
            (f"Bold *{DOCS}* here", f"Bold *{anchor(DOCS)}* here"),
            (f"Code `{wiki}` here", f"Code `{anchor(wiki)}` here"),
            (f"Run `curl {DOCS}` now", f"Run `curl {anchor(DOCS)}` now"),
            (f"In _{DOCS}_ and ~~{DOCS}~~", f"In _{anchor(DOCS)}_ and ~~{anchor(DOCS)}~~"),
            # An apostrophe inside a link, and an "_" ending one with no mark before it, are the address's own.
            ("Ask https://example.org/o'brien now", f"Ask {anchor('https://example.org/o&#x27;brien')} now"),
            (f"File {drive} and _{drive}_", f"File {anchor(drive)} and _{anchor(drive)}_"),
        )
        for body, expected in cases:
            with self.subTest(body):
                self.assertIn(expected, render_reply_html(body))

    def test_a_link_keeps_letters_of_any_script_up_to_other_punctuation_a_space_or_glued_cjk_text(self):
        # Read as printable ASCII only, a link ended at its first other letter ("…/wiki/Universit").
        german = "https://de.wikipedia.org/wiki/Universität_von_Kalifornien,_Merced"
        chinese = "https://zh.wikipedia.org/wiki/加利福尼亚大学默塞德分校"
        japanese = "https://ja.wikipedia.org/wiki/マーセド_(カリフォルニア州)"
        search = "https://www.baidu.com/s?wd=加州大学"
        cases = (
            (f"German: {german} and more", f"German: {anchor(german)} and more"),
            (f"中文：{chinese} 好", f"中文：{anchor(chinese)} 好"),
            (f"见{chinese}。下一句", f"见{anchor(chinese)}。下一句"),
            (f"“{german}”, «{german}»", f"“{anchor(german)}”, «{anchor(german)}»"),
            (f"{german}\u00a0next", f"{anchor(german)}\u00a0next"),  # a no-break space
            (f"{japanese}と{search}，好", f"{anchor(japanese)}と{anchor(search)}，好"),
            # Chinese, Japanese or Korean text glued to the link's last ASCII character goes on with the sentence.
            (f"詳細は{DOCS}をご覧ください", f"詳細は{anchor(DOCS)}をご覧ください"),
            (f"{DOCS}를 확인하세요", f"{anchor(DOCS)}를 확인하세요"),
        )
        for body, expected in cases:
            with self.subTest(body):
                self.assertIn(expected, render_reply_html(body))

    def test_each_line_of_the_quote_breaks_once(self):
        # The quote is shown "white-space: pre-wrap": a <br> and a line break both would break the line twice.
        html = render_reply_html("Thanks", quoted_text="Hello,\r\n\r\nour team\nThanks,\nQuinn")

        self.assertIn("Hello,<br><br>our team<br>Thanks,<br>Quinn</div>", html)

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
