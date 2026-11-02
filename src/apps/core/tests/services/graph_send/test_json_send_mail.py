"""Credential mail through Microsoft Graph: JSON ``sendMail`` with ``saveToSentItems`` false, no Sent Items copy.

A MIME ``sendMail`` request always files a copy in the sender mailbox's Sent Items, where anyone who can read the
folder could use a sign-in code or login link. Messages marked ``keep_sent_copy=False`` therefore go as JSON.
"""

import base64
import json

from django.test import SimpleTestCase

from apps.core.services.email import EmailAttachment, PermanentEmailDeliveryError
from apps.core.services.email.graph import json_message
from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.services.test_email_graph import (
    ACCESS_TOKEN,
    MAILBOX,
    PROVIDER_LOGGER,
    GraphFixtureMixin,
    graph_response,
    make_provider,
    sent_mime,
    simple_message,
    ticket_message,
)

JSON_LOGGER = "apps.core.services.email.graph.json_message"


def credential_message(**overrides):
    values = {"keep_sent_copy": False, "html_body": "<p>Your code is 482913</p>", "text_body": None}
    return simple_message(**{**values, **overrides})


class JsonSendMailRequestTests(GraphFixtureMixin, SimpleTestCase):
    def send(self, message, **provider_overrides):
        return make_provider(**provider_overrides).send(message)

    def sent_json(self):
        return json.loads(self.fake.send_requests[-1].body)

    def test_credential_mail_is_json_with_save_to_sent_items_false(self):
        result = self.send(credential_message())

        request = self.fake.send_requests[0]
        self.assertEqual(request.path, f"/v1.0/users/{MAILBOX}/sendMail")
        self.assertEqual(request.headers["Content-Type"], "application/json")
        self.assertEqual(request.headers["Authorization"], f"Bearer {ACCESS_TOKEN}")
        body = json.loads(request.body)
        self.assertEqual(set(body), {"message", "saveToSentItems"})
        self.assertIs(body["saveToSentItems"], False)
        self.assertEqual(
            body["message"],
            {
                "subject": "Subject",
                "body": {"contentType": "HTML", "content": "<p>Your code is 482913</p>"},
                "from": {"emailAddress": {"address": MAILBOX, "name": "Innovate to Grow"}},
                "toRecipients": [{"emailAddress": {"address": "to@example.com"}}],
            },
        )
        # Graph assigns no id and the JSON form sets no Message-ID header, so none is reported.
        self.assertEqual((result.provider, result.message_id, result.accepted), ("graph", "", True))

    def test_ordinary_mail_still_goes_as_mime_and_keeps_its_headers(self):
        self.send(ticket_message())

        request = self.fake.send_requests[0]
        self.assertEqual(request.headers["Content-Type"], "text/plain")
        self.assertEqual(sent_mime(request)["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")

    def test_text_only_mail_is_sent_as_text(self):
        self.send(credential_message(html_body=None, text_body="Code: 482913"))

        self.assertEqual(self.sent_json()["message"]["body"], {"contentType": "Text", "content": "Code: 482913"})

    def test_the_html_body_wins_when_both_bodies_exist(self):
        self.send(credential_message(text_body="plain", html_body="<p>html</p>"))

        self.assertEqual(self.sent_json()["message"]["body"], {"contentType": "HTML", "content": "<p>html</p>"})

    def test_maps_every_recipient_list_and_reply_to(self):
        message = credential_message(
            to=("a@example.com", "Bea Example <b@example.com>"),
            cc=("c@example.com",),
            bcc=("d@example.com",),
            reply_to=("replies@example.com",),
        )

        self.send(message)

        sent = self.sent_json()["message"]
        self.assertEqual(
            sent["toRecipients"],
            [
                {"emailAddress": {"address": "a@example.com"}},
                {"emailAddress": {"address": "b@example.com", "name": "Bea Example"}},
            ],
        )
        self.assertEqual(sent["ccRecipients"], [{"emailAddress": {"address": "c@example.com"}}])
        # Unlike MIME, the JSON form has its own Bcc list, so Bcc is delivered rather than refused.
        self.assertEqual(sent["bccRecipients"], [{"emailAddress": {"address": "d@example.com"}}])
        self.assertEqual(sent["replyTo"], [{"emailAddress": {"address": "replies@example.com"}}])

    def test_a_blank_from_name_is_left_out(self):
        self.send(credential_message(), from_name="")

        self.assertEqual(self.sent_json()["message"]["from"], {"emailAddress": {"address": MAILBOX}})

    def test_attachments_become_file_attachments_and_inline_ones_keep_their_content_id(self):
        message = credential_message(
            html_body='<p><img src="cid:ticket-barcode"></p>',
            attachments=(
                EmailAttachment("ticket-barcode.png", b"\x89PNG-bytes", "image/png", "inline", "ticket-barcode"),
                EmailAttachment("logo.png", b"logo", "image/png", "inline", "<logo@i2g>"),
                EmailAttachment("photo.png", b"photo", "image/png", "inline"),
                EmailAttachment("event.ics", b"BEGIN:VCALENDAR", "text/calendar"),
            ),
        )

        self.send(message)

        kind = json_message.FILE_ATTACHMENT_TYPE
        self.assertEqual(
            self.sent_json()["message"]["attachments"],
            [
                {
                    "@odata.type": kind,
                    "name": "ticket-barcode.png",
                    "contentType": "image/png",
                    "contentBytes": base64.b64encode(b"\x89PNG-bytes").decode(),
                    "isInline": True,
                    "contentId": "ticket-barcode",
                },
                {
                    "@odata.type": kind,
                    "name": "logo.png",
                    "contentType": "image/png",
                    "contentBytes": base64.b64encode(b"logo").decode(),
                    "isInline": True,
                    "contentId": "logo@i2g",
                },
                {
                    "@odata.type": kind,
                    "name": "photo.png",
                    "contentType": "image/png",
                    "contentBytes": base64.b64encode(b"photo").decode(),
                    "isInline": True,
                    "contentId": "photo.png",
                },
                {
                    "@odata.type": kind,
                    "name": "event.ics",
                    "contentType": "text/calendar",
                    "contentBytes": base64.b64encode(b"BEGIN:VCALENDAR").decode(),
                },
            ],
        )

    def test_only_x_headers_are_carried_and_the_others_are_logged_by_name(self):
        message = credential_message(
            headers={
                "X-I2G-Purpose": "login",
                "x-lower": "kept",
                "List-Unsubscribe": "<https://example.com/u/secret-token>",
                "In-Reply-To": "<original@example.com>",
            }
        )

        with self.assertLogs(JSON_LOGGER, "WARNING") as logs:
            self.send(message)

        self.assertEqual(
            self.sent_json()["message"]["internetMessageHeaders"],
            [{"name": "X-I2G-Purpose", "value": "login"}, {"name": "x-lower", "value": "kept"}],
        )
        self.assertEqual(
            logs.output,
            [
                f"WARNING:{JSON_LOGGER}:Microsoft Graph JSON sendMail cannot carry these headers, so they were "
                "left out: List-Unsubscribe, In-Reply-To"
            ],
        )
        self.assertNotIn("secret-token", "\n".join(logs.output))

    def test_no_headers_means_no_header_list(self):
        self.send(credential_message())

        self.assertNotIn("internetMessageHeaders", self.sent_json()["message"])

    def test_non_ascii_text_is_sent_as_utf8(self):
        self.send(credential_message(subject="Caf\N{LATIN SMALL LETTER E WITH ACUTE} \N{EN DASH} code"))

        body = self.fake.send_requests[0].body
        self.assertIn("Caf\N{LATIN SMALL LETTER E WITH ACUTE}".encode(), body)
        self.assertEqual(
            self.sent_json()["message"]["subject"], "Caf\N{LATIN SMALL LETTER E WITH ACUTE} \N{EN DASH} code"
        )

    def test_the_body_carries_no_key_material(self):
        self.send(credential_message())

        for line in private_key_lines():
            self.assertNotIn(line.encode(), self.fake.send_requests[0].body)

    def test_a_refused_json_send_is_classified_like_a_mime_send(self):
        self.fake.script(send=graph_response(400))

        with (
            self.assertLogs(PROVIDER_LOGGER, "WARNING"),
            self.assertRaisesMessage(PermanentEmailDeliveryError, "Microsoft Graph rejected the request"),
        ):
            self.send(credential_message())


class JsonSendMailCompositionTests(GraphFixtureMixin, SimpleTestCase):
    """Composition problems are permanent and refused before a token is requested or anything is sent."""

    def assert_refused(self, message, text):
        with self.assertRaisesMessage(PermanentEmailDeliveryError, text):
            make_provider().send(message)
        self.assertEqual(self.fake.requests, [])

    def test_refuses_mail_without_recipients_or_body(self):
        self.assert_refused(credential_message(to=()), "Email has no recipients.")
        self.assert_refused(credential_message(html_body=None, text_body=None), "Email has no body.")

    def test_refuses_inline_attachments_without_an_html_body(self):
        inline = EmailAttachment("a.png", b"x", "image/png", disposition="inline")

        self.assert_refused(
            credential_message(html_body=None, text_body="t", attachments=(inline,)),
            "Inline email attachments require an HTML body.",
        )

    def test_refuses_an_invalid_attachment_content_type(self):
        broken = EmailAttachment("a.bin", b"x", "not-a-type")

        self.assert_refused(credential_message(attachments=(broken,)), "Invalid attachment content type")

    def test_refuses_headers_the_builders_manage_and_malformed_headers(self):
        self.assert_refused(credential_message(headers={"Reply-To": "x@example.com"}), "is managed by the delivery")
        self.assert_refused(credential_message(headers={"X-Bad": "a\r\nBcc: evil@example.com"}), "header is malformed")
        self.assert_refused(credential_message(headers={"X Bad": "value"}), "header is malformed")

    def test_refuses_recipients_that_are_not_addresses(self):
        for recipient in ("not an address", "", "a@example.com\nBcc: evil@example.com"):
            with self.subTest(recipient=recipient):
                self.assert_refused(credential_message(to=(recipient,)), "An email recipient address is invalid.")

    def test_unencodable_text_is_a_composition_error(self):
        self.assert_refused(credential_message(subject="lone \udc80 surrogate"), "could not be composed")
