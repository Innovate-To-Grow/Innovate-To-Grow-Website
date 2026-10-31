"""Inbox replies cannot inject HTML: the success banner is built with ``textContent`` and addresses must be plain.

The reply form is pre-filled with the original sender's address, which a sender controls. A quoted local part such
as ``"x <img src=x onerror=...>"@evil.example`` is a valid RFC 5322 address that Python's ``parseaddr`` keeps
verbatim, so it used to come back in the AJAX answer and reach ``innerHTML`` in the admin origin.
"""

import email
import email.policy
import re
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.services.inbox import graph_backend
from apps.mail.services.inbox.reply import REPLY_INVALID_ADDRESS_MESSAGE, send_reply

LIST_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "admin" / "mail" / "inbox" / "list.html"
DELIVER = "apps.mail.services.inbox.reply.deliver_email"
PAYLOAD = "<img src=x onerror=alert(document.domain)>"
CRAFTED_MIME = (
    f'From: "Jane" <"jane          {PAYLOAD}"@evil.example>\r\n'
    "To: i2g@ucmerced.edu\r\n"
    "Subject: Question\r\n"
    "Message-ID: <q-1@evil.example>\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n\r\n"
    "Hello"
).encode()
# What the page may assign to ``innerHTML``: fixed markup, or a fragment the server rendered with autoescaping.
_INNER_HTML_RE = re.compile(r"\.innerHTML\s*=\s*(?P<value>.+?);\s*$")
_SAFE_INNER_HTML = re.compile(r"'[^'+]*'|html|newList\.innerHTML|newSplit\.outerHTML")


class ReplyBannerTemplateTests(SimpleTestCase):
    def setUp(self):
        self.source = LIST_TEMPLATE.read_text(encoding="utf-8")

    def test_no_server_value_is_assigned_to_inner_html(self):
        assignments = [match["value"] for line in self.source.splitlines() if (match := _INNER_HTML_RE.search(line))]

        self.assertTrue(assignments)
        for value in assignments:
            with self.subTest(value=value):
                self.assertTrue(_SAFE_INNER_HTML.fullmatch(value.strip()), value)
        self.assertNotRegex(self.source, r"innerHTML[^;]*data\.")

    def test_the_success_message_is_inserted_as_text(self):
        self.assertIn("showReplySent(replyArea, data.message);", self.source)
        body = self.source.split("function showReplySent", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("label.textContent =", body)
        self.assertNotIn("innerHTML", body)


class ReplyAddressTests(TestCase):
    def setUp(self):
        cache.clear()
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="i2g@ucmerced.edu", from_name="I2G")

    def reply(self, to_email, cc_email=""):
        with patch(DELIVER) as deliver, patch.object(EmailServiceConfig, "delivery_configured", True):
            error = send_reply(to_email=to_email, subject="Re: Question", reply_body="Thanks", cc_email=cc_email)
        return error, deliver

    def test_quoted_local_parts_display_names_and_markup_are_refused_before_sending(self):
        refused = [
            f'"jane {PAYLOAD}"@evil.example',
            '"jane"@evil.example',
            "Jane <jane@example.com>",
            "jane@example.com (Jane)",
            "o'brien@example.com",
            "a&b@example.com",
            "jane@[192.0.2.1]",
            "jane@localhost",
            "jane@example.com\r\nBcc: evil@example.com",
            "",
        ]
        for address in refused:
            with self.subTest(to=address):
                error, deliver = self.reply(address)

                self.assertEqual(error, REPLY_INVALID_ADDRESS_MESSAGE)
                deliver.assert_not_called()

    def test_every_cc_address_is_checked(self):
        error, deliver = self.reply("ada@example.com", cc_email=f'ok@example.com, "x {PAYLOAD}"@evil.example')

        self.assertEqual(error, REPLY_INVALID_ADDRESS_MESSAGE)
        deliver.assert_not_called()

    def test_plain_addresses_are_sent(self):
        error, deliver = self.reply("first.last+tag@mail.example.com", cc_email="ops@example.org, a_b-c@example.co.uk")

        self.assertEqual(error, "")
        message = deliver.call_args.args[0]
        self.assertEqual(message.to, ("first.last+tag@mail.example.com",))
        self.assertEqual(message.cc, ("ops@example.org", "a_b-c@example.co.uk"))


class CraftedSenderReplyTests(TestCase):
    """The F25 scenario end to end: a crafted From parsed by the Graph backend, then a one-click reply."""

    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="i2g@ucmerced.edu", from_name="I2G")
        message = email.message_from_bytes(CRAFTED_MIME, policy=email.policy.default)
        self.msg = {**graph_backend._detail("AAMkAGI2THVSAAA=", message), "from_own_mailbox": False}

    def test_the_crafted_address_survives_parsing(self):
        self.assertIn(PAYLOAD, self.msg["from_email"])

    def test_a_reply_to_it_is_refused_and_the_answer_carries_no_markup(self):
        url = reverse("admin:mail_inbox_reply_fragment", args=[self.msg["uid"]])

        with (
            patch("apps.mail.admin.inbox.services.fetch_inbox_message", return_value=self.msg),
            patch(DELIVER) as deliver,
            patch.object(EmailServiceConfig, "delivery_configured", True),
        ):
            answer = self.client.post(url, {"reply_body": "Thanks"})

        self.assertEqual(answer.json(), {"ok": False, "error": REPLY_INVALID_ADDRESS_MESSAGE})
        self.assertNotIn(b"<img", answer.content)
        deliver.assert_not_called()
