import base64

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    TICKET_SUBJECT,
    GraphFixtureMixin,
    make_provider,
    sent_mime,
    simple_message,
    ticket_message,
)


class GraphProviderSendTests(GraphFixtureMixin, SimpleTestCase):
    def send(self, message=None, **provider_overrides):
        return make_provider(**provider_overrides).send(message or simple_message())

    def test_submits_the_message_to_send_mail_with_a_bearer_token(self):
        result = self.send()

        self.assertEqual(result.provider, "graph")
        self.assertTrue(result.accepted)
        self.assertEqual(
            [request.host for request in self.fake.requests], ["login.microsoftonline.com", "graph.microsoft.com"]
        )
        request = self.fake.send_requests[0]
        self.assertEqual(request.path, "/v1.0/users/sender@contoso.com/sendMail")
        self.assertEqual(request.headers["Authorization"], f"Bearer {ACCESS_TOKEN}")
        self.assertEqual(request.headers["Content-Type"], "text/plain")
        self.assertEqual(request.headers["Accept"], "application/json")

    def test_request_body_is_one_line_of_base64_mime(self):
        self.send(simple_message(subject="Greetings"))

        request = self.fake.send_requests[0]
        self.assertNotIn(b"\n", request.body)
        self.assertEqual(sent_mime(request)["Subject"], "Greetings")

    def test_mime_is_sent_with_crlf_line_endings(self):
        # Exchange decodes a quoted-printable soft break only at CRLF; a bare LF there corrupted every long line.
        long_line = '<p style="' + "x" * 200 + '">Innovate to Grow</p>'
        self.send(simple_message(text_body=None, html_body=long_line))

        raw = base64.b64decode(self.fake.send_requests[0].body, validate=True)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF remains")
        self.assertIn(b"=\r\n", raw)
        content = sent_mime(self.fake.send_requests[0]).get_content()
        self.assertEqual(content.replace("\r\n", "\n"), long_line + "\n")

    def test_result_message_id_is_the_mime_message_id(self):
        result = self.send()

        mime_message_id = str(sent_mime(self.fake.send_requests[0])["Message-ID"])
        self.assertEqual(result.message_id, mime_message_id)
        self.assertTrue(result.message_id.startswith("<") and result.message_id.endswith(">"))

    def test_every_send_gets_its_own_message_id(self):
        provider = make_provider()

        first = provider.send(simple_message())
        second = provider.send(simple_message())

        self.assertNotEqual(first.message_id, second.message_id)

    def test_mailbox_is_percent_encoded_into_the_path_but_keeps_the_at_sign(self):
        cases = [
            ("sender@contoso.com", "sender@contoso.com"),
            ("user+tag@contoso.com", "user%2Btag@contoso.com"),
            ("o'brien@contoso.com", "o%27brien@contoso.com"),
            # Valid for the address validator, yet it must not be able to add path segments or a query string.
            ("a/b?c#d@contoso.com", "a%2Fb%3Fc%23d@contoso.com"),
            ("72f988bf-86f1-41af-91ab-2d7cd011db47", "72f988bf-86f1-41af-91ab-2d7cd011db47"),
        ]
        for mailbox, segment in cases:
            with self.subTest(mailbox=mailbox):
                self.script()

                self.send(mailbox=mailbox)

                self.assertEqual(self.fake.send_requests[0].path, f"/v1.0/users/{segment}/sendMail")

    def test_addressing_and_threading_headers_survive_the_mime_round_trip(self):
        self.send(ticket_message())

        mime = sent_mime(self.fake.send_requests[0])
        self.assertEqual(mime["Subject"], TICKET_SUBJECT)
        self.assertEqual(mime["From"], "Innovate to Grow <sender@contoso.com>")
        self.assertEqual(mime["To"], "to1@example.com, to2@example.com")
        self.assertEqual(mime["Cc"], "cc@example.com")
        self.assertEqual(mime["Reply-To"], "replies@example.com")
        # A long header is folded after its name on the wire, so unfold it before comparing.
        unsubscribe = " ".join(str(mime["List-Unsubscribe"]).split())
        self.assertEqual(unsubscribe, "<mailto:unsubscribe@example.com>, <https://example.com/unsubscribe/abc>")
        self.assertEqual(mime["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertEqual(mime["In-Reply-To"], "<original@example.com>")
        self.assertEqual(mime["References"], "<root@example.com> <original@example.com>")
        self.assertIsNone(mime["Bcc"])

    def test_from_header_is_the_bare_address_without_a_display_name(self):
        self.send(from_name="")

        self.assertEqual(sent_mime(self.fake.send_requests[0])["From"], "sender@contoso.com")

    def test_from_header_uses_the_from_address_rather_than_the_sending_mailbox(self):
        self.send(mailbox="shared@contoso.com", from_email="noreply@example.com", from_name="")

        request = self.fake.send_requests[0]
        self.assertEqual(request.path, "/v1.0/users/shared@contoso.com/sendMail")
        self.assertEqual(sent_mime(request)["From"], "noreply@example.com")

    def test_html_inline_image_and_attachment_survive_the_mime_round_trip(self):
        self.send(ticket_message())

        mime = sent_mime(self.fake.send_requests[0])
        html = mime.get_body(preferencelist=("html",))
        self.assertIn('<img src="cid:qr-code">', html.get_content())
        parts = {part.get_filename(): part for part in mime.walk() if part.get_filename()}
        inline = parts["qr.png"]
        self.assertEqual(inline.get_content_disposition(), "inline")
        self.assertEqual(inline["Content-ID"], "<qr-code>")
        self.assertEqual(inline.get_content_type(), "image/png")
        self.assertEqual(inline.get_payload(decode=True), b"inline-image-bytes")
        attachment = parts["ticket.ics"]
        self.assertEqual(attachment.get_content_disposition(), "attachment")
        self.assertEqual(attachment.get_payload(decode=True), b"BEGIN:VCALENDAR")

    def test_text_and_html_bodies_are_sent_as_alternatives(self):
        self.send(ticket_message())

        mime = sent_mime(self.fake.send_requests[0])
        self.assertIn("multipart/alternative", [part.get_content_type() for part in mime.walk()])
        self.assertEqual(mime.get_body(preferencelist=("plain",)).get_content().strip(), "Plain body")
        self.assertIn("HTML body", mime.get_body(preferencelist=("html",)).get_content())

    def test_html_only_message_has_no_plain_part(self):
        self.send(simple_message(text_body=None, html_body="<p>Only HTML</p>"))

        mime = sent_mime(self.fake.send_requests[0])
        self.assertEqual(mime.get_content_type(), "text/html")
        self.assertIn("Only HTML", mime.get_content())

    def test_consecutive_sends_reuse_one_access_token(self):
        provider = make_provider()

        provider.send(simple_message())
        provider.send(simple_message())

        self.assertEqual(len(self.fake.token_requests), 1)
        self.assertEqual(len(self.fake.send_requests), 2)

    def test_timeout_reaches_both_the_token_and_the_send_request(self):
        self.send()
        self.assertEqual(
            [request.timeout for request in self.fake.requests], [settings.GRAPH_REQUEST_TIMEOUT_SECONDS] * 2
        )

        self.script()
        self.send(timeout=7)
        self.assertEqual([request.timeout for request in self.fake.requests], [7, 7])

    def test_credentials_stay_out_of_the_send_request_url_and_body(self):
        self.send()

        request = self.fake.send_requests[0]
        self.assertNotIn(ACCESS_TOKEN, request.path)
        self.assertNotIn(ACCESS_TOKEN.encode(), request.body)
        for line in private_key_lines():
            for sent in (request.path, request.body.decode("ascii"), "".join(request.headers.values())):
                self.assertNotIn(line, sent)
        carrying_the_token = [name for name, value in request.headers.items() if ACCESS_TOKEN in value]
        self.assertEqual(carrying_the_token, ["Authorization"])
