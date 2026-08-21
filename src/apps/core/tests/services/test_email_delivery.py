from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from django.test import SimpleTestCase

from apps.core.services.email import (
    EmailAttachment,
    EmailDeliveryService,
    EmailMessage,
    PermanentEmailDeliveryError,
    SESProvider,
    SMTPProvider,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    resolve_provider,
)
from apps.core.services.email.mime import build_mime_message


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


class SESTests(SimpleTestCase):
    def setUp(self):
        self.message = EmailMessage("Subject", ("to@example.com",), text_body="Body", bcc=("bcc@example.com",))
        self.credentials = SimpleNamespace(region="us-west-2", access_key_id="key", secret_access_key="secret")

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_sends_raw_message_with_explicit_credentials(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials
        client_factory.return_value.send_raw_email.return_value = {"MessageId": "ses-id"}
        provider = SESProvider(from_email="from@example.com", from_name="Name", configuration_set="events")

        result = provider.send(self.message)

        self.assertEqual(result.message_id, "ses-id")
        client_factory.assert_called_once()
        call = client_factory.call_args
        self.assertEqual(call.kwargs["aws_access_key_id"], "key")
        send = client_factory.return_value.send_raw_email.call_args.kwargs
        self.assertEqual(send["Destinations"], ["to@example.com", "bcc@example.com"])
        self.assertEqual(send["ConfigurationSetName"], "events")
        self.assertNotIn(b"Bcc:", send["RawMessage"]["Data"])

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_callback_failure_is_not_reclassified(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials

        with self.assertRaisesRegex(RuntimeError, "claim lost"):
            SESProvider(from_email="from@example.com").send(
                self.message,
                before_provider_call=MagicMock(side_effect=RuntimeError("claim lost")),
            )

        client_factory.return_value.send_raw_email.assert_not_called()

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_classifies_aws_failures(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials
        cases = [
            (EndpointConnectionError(endpoint_url="https://ses"), TransientEmailDeliveryError),
            (ReadTimeoutError(endpoint_url="https://ses", error="timeout"), UncertainEmailDeliveryError),
            (
                ClientError(
                    {"Error": {"Code": "MessageRejected"}, "ResponseMetadata": {"HTTPStatusCode": 400}}, "SendRawEmail"
                ),
                PermanentEmailDeliveryError,
            ),
        ]
        for error, expected in cases:
            client_factory.return_value.send_raw_email.side_effect = error
            with self.subTest(error=type(error).__name__), self.assertRaises(expected):
                SESProvider(from_email="from@example.com").send(self.message)


class SMTPTests(SimpleTestCase):
    def setUp(self):
        self.message = EmailMessage(
            "Subject", ("to@example.com",), text_body="Body", cc=("cc@example.com",), bcc=("bcc@example.com",)
        )

    @patch("apps.core.services.email.smtp.ssl.create_default_context")
    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_starttls_auth_and_envelope_recipients(self, smtp_class, context_factory):
        client = smtp_class.return_value.__enter__.return_value
        client.send_message.return_value = {}
        result = SMTPProvider(
            host="smtp.example.com", port=587, from_email="from@example.com", username="user", password="pass"
        ).send(self.message)

        smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
        client.starttls.assert_called_once_with(context=context_factory.return_value)
        client.login.assert_called_once_with("user", "pass")
        sent = client.send_message.call_args
        self.assertEqual(sent.kwargs["to_addrs"], ["to@example.com", "cc@example.com", "bcc@example.com"])
        self.assertIsNone(sent.args[0]["Bcc"])
        self.assertEqual(result.message_id, str(sent.args[0]["Message-ID"]))

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_temporary_sender_refusal_is_transient(self, smtp_class):
        import smtplib

        smtp_class.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPSenderRefused(
            450, b"try later", "from@example.com"
        )
        with self.assertRaises(TransientEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_partial_recipient_acceptance_is_uncertain(self, smtp_class):
        smtp_class.return_value.__enter__.return_value.send_message.return_value = {
            "bcc@example.com": (550, b"rejected")
        }

        with self.assertRaises(UncertainEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_disconnect_during_send_is_uncertain(self, smtp_class):
        import smtplib

        smtp_class.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPServerDisconnected()
        with self.assertRaises(UncertainEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )


class RegistryFacadeTests(SimpleTestCase):
    @patch("apps.core.models.SMTPProviderConfig.load")
    def test_resolves_smtp_config_without_fallback(self, load_smtp):
        load_smtp.return_value = SimpleNamespace(
            is_configured=True,
            host="smtp.example.com",
            port=465,
            username="",
            password="",
            use_tls=False,
            use_ssl=True,
            timeout=10,
        )
        config = SimpleNamespace(
            provider="smtp",
            from_email="from@example.com",
            from_name="Name",
        )
        self.assertIsInstance(resolve_provider(config), SMTPProvider)
        with self.assertRaises(PermanentEmailDeliveryError):
            resolve_provider(SimpleNamespace(provider="unknown"))

    def test_facade_rejects_inactive_config(self):
        message = EmailMessage("Subject", ("to@example.com",), text_body="Body")
        with self.assertRaises(PermanentEmailDeliveryError):
            EmailDeliveryService(SimpleNamespace(is_active=False)).send(message)
