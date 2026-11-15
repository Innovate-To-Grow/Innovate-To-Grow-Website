from django.test import SimpleTestCase

from apps.core.services.email import (
    EmailAttachment,
    EmailMessage,
    PermanentEmailDeliveryError,
)
from apps.core.services.email.sending.mime import build_mime_message


class MimeTests(SimpleTestCase):
    def test_builds_alternative_attachment_and_hides_bcc(self):
        mime = build_mime_message(
            EmailMessage(
                subject="Hello",
                to=("to@example.com",),
                cc=("cc@example.com",),
                bcc=("hidden@example.com",),
                text_body="Plain",
                html_body="<b>HTML</b>",
                attachments=(EmailAttachment("data.txt", b"data", "text/plain"),),
            ),
            from_email="sender@example.com",
            from_name="Sender",
        )
        self.assertEqual(mime["From"], "Sender <sender@example.com>")
        self.assertIsNone(mime["Bcc"])
        self.assertTrue(mime["Message-ID"])
        self.assertEqual(len(list(mime.iter_attachments())), 1)

    def test_builds_inline_related_attachment_with_bracketed_content_id(self):
        mime = build_mime_message(
            EmailMessage(
                subject="Ticket",
                to=("to@example.com",),
                html_body='<img src="cid:ticket-barcode">',
                attachments=(
                    EmailAttachment(
                        "ticket.png",
                        b"image",
                        "image/png",
                        disposition="inline",
                        content_id="ticket-barcode",
                    ),
                ),
            ),
            from_email="sender@example.com",
        )

        inline = next(mime.iter_attachments())
        self.assertEqual(inline["Content-ID"], "<ticket-barcode>")
        self.assertEqual(inline.get_content_disposition(), "inline")
        self.assertIn("multipart/related", mime.as_string())

    def test_requires_recipient_and_body(self):
        with self.assertRaises(PermanentEmailDeliveryError):
            build_mime_message(EmailMessage("x", (), text_body="body"), from_email="from@example.com")
        with self.assertRaises(PermanentEmailDeliveryError):
            build_mime_message(EmailMessage("x", ("to@example.com",)), from_email="from@example.com")

    def test_sets_reply_to_header(self):
        mime = build_mime_message(
            EmailMessage(
                subject="Hello",
                to=("to@example.com",),
                text_body="Body",
                reply_to=("reply@example.com", "also@example.com"),
            ),
            from_email="from@example.com",
        )
        self.assertEqual(mime["Reply-To"], "reply@example.com, also@example.com")

    def test_rejects_protected_headers(self):
        with self.assertRaises(PermanentEmailDeliveryError):
            build_mime_message(
                EmailMessage(
                    subject="Hello",
                    to=("to@example.com",),
                    text_body="Body",
                    headers={"Subject": "spoofed"},
                ),
                from_email="from@example.com",
            )

    def test_inline_attachment_requires_html_body(self):
        with self.assertRaises(PermanentEmailDeliveryError):
            build_mime_message(
                EmailMessage(
                    subject="Hello",
                    to=("to@example.com",),
                    text_body="Plain only",
                    attachments=(
                        EmailAttachment(
                            "logo.png",
                            b"image",
                            "image/png",
                            disposition="inline",
                            content_id="logo",
                        ),
                    ),
                ),
                from_email="from@example.com",
            )

    def test_rejects_invalid_attachment_content_type(self):
        with self.assertRaises(PermanentEmailDeliveryError):
            build_mime_message(
                EmailMessage(
                    subject="Hello",
                    to=("to@example.com",),
                    text_body="Body",
                    attachments=(EmailAttachment("bad.bin", b"x", "not-a-type"),),
                ),
                from_email="from@example.com",
            )
