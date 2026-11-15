from django.test import SimpleTestCase

from apps.core.services.email import EmailAttachment, PermanentEmailDeliveryError
from apps.core.tests.services.graph.provider.test_email_graph import GraphFixtureMixin, make_provider
from apps.core.tests.services.graph.send.test_json_send_mail import credential_message


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
