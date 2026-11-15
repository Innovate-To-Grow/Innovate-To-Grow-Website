import base64

from apps.core.services.email import EmailAttachment, PermanentEmailDeliveryError
from apps.core.services.email.graph import json_message
from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.services.graph_send.test_json_send_mail import (
    JSON_LOGGER,
    _JsonSendMailRequestCase,
    credential_message,
)
from apps.core.tests.services.test_email_graph import (
    PROVIDER_LOGGER,
    graph_response,
)


class JsonSendMailRequestTests(_JsonSendMailRequestCase):
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
