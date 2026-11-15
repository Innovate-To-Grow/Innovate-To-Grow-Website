from unittest.mock import patch

from apps.core.services.email import (
    PermanentEmailDeliveryError,
    SMTPProvider,
    TransientEmailDeliveryError,
)
from apps.core.tests.services.email.smtp.test_smtp import _SMTPCase


class SMTPTests(_SMTPCase):
    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_permanent_sender_refusal_and_not_supported(self, smtp_class):
        import smtplib

        client = smtp_class.return_value
        client.send_message.side_effect = smtplib.SMTPSenderRefused(550, b"no", "from@example.com")
        with self.assertRaises(PermanentEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

        client.send_message.side_effect = smtplib.SMTPNotSupportedError("no auth")
        with self.assertRaises(PermanentEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )

    @patch("apps.core.services.email.smtp.smtplib.SMTP")
    def test_unreachable_server_before_submit_is_transient(self, smtp_class):
        smtp_class.side_effect = ConnectionError("refused")
        with self.assertRaises(TransientEmailDeliveryError):
            SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message
            )
