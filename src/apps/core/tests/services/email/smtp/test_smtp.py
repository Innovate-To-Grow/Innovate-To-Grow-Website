import ssl
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.core.services.email import (
    EmailMessage,
    PermanentEmailDeliveryError,
    SMTPProvider,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)


class _SMTPCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.message = EmailMessage(
            "Subject", ("to@example.com",), text_body="Body", cc=("cc@example.com",), bcc=("bcc@example.com",)
        )


class SMTPTests(_SMTPCase):
    @patch("apps.core.services.email.smtp.ssl.create_default_context")
    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_starttls_auth_and_envelope_recipients(self, smtp_class, context_factory):
        client = smtp_class.return_value
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

        smtp_class.return_value.send_message.side_effect = smtplib.SMTPSenderRefused(
            450, b"try later", "from@example.com"
        )
        with self.assertRaises(TransientEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_partial_recipient_acceptance_is_uncertain(self, smtp_class):
        smtp_class.return_value.send_message.return_value = {"bcc@example.com": (550, b"rejected")}

        with self.assertRaises(UncertainEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_disconnect_during_send_is_uncertain(self, smtp_class):
        import smtplib

        smtp_class.return_value.send_message.side_effect = smtplib.SMTPServerDisconnected()
        with self.assertRaises(UncertainEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    def test_rejects_tls_and_ssl_together(self):
        with self.assertRaises(ValueError):
            SMTPProvider(
                host="smtp.example.com",
                port=465,
                from_email="from@example.com",
                use_tls=True,
                use_ssl=True,
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP_SSL")
    def test_uses_ssl_without_starttls(self, smtp_ssl_class):
        client = smtp_ssl_class.return_value
        client.send_message.return_value = {}

        result = SMTPProvider(
            host="smtp.example.com",
            port=465,
            from_email="from@example.com",
            use_tls=False,
            use_ssl=True,
        ).send(self.message)

        smtp_ssl_class.assert_called_once()
        self.assertEqual(smtp_ssl_class.call_args.args, ("smtp.example.com", 465))
        self.assertEqual(smtp_ssl_class.call_args.kwargs["timeout"], 30)
        context = smtp_ssl_class.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        client.starttls.assert_not_called()
        self.assertTrue(result.message_id)

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_recipients_refused_4xx_is_transient(self, smtp_class):
        import smtplib

        smtp_class.return_value.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"to@example.com": (450, b"try later")}
        )
        with self.assertRaises(TransientEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_recipients_refused_5xx_is_permanent(self, smtp_class):
        import smtplib

        smtp_class.return_value.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"to@example.com": (550, b"user unknown")}
        )
        with self.assertRaises(PermanentEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_data_error_4xx_and_5xx(self, smtp_class):
        import smtplib

        client = smtp_class.return_value
        client.send_message.side_effect = smtplib.SMTPDataError(451, b"try later")
        with self.assertRaises(TransientEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

        client.send_message.side_effect = smtplib.SMTPDataError(554, b"rejected")
        with self.assertRaises(PermanentEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_response_exception_4xx_and_5xx(self, smtp_class):
        import smtplib

        client = smtp_class.return_value
        client.send_message.side_effect = smtplib.SMTPResponseException(421, b"closing")
        with self.assertRaises(TransientEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

        client.send_message.side_effect = smtplib.SMTPResponseException(500, b"error")
        with self.assertRaises(PermanentEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_generic_smtp_exception_before_and_after_submit(self, smtp_class):
        import smtplib

        client = smtp_class.return_value
        client.starttls.side_effect = smtplib.SMTPException("tls failed")
        with self.assertRaises(PermanentEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=True).send(
                self.message
            )

        client.starttls.side_effect = None
        client.send_message.side_effect = smtplib.SMTPException("send failed")
        with self.assertRaises(UncertainEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )
