import smtplib
import ssl
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.core.services.email import (
    EmailMessage,
    PermanentEmailDeliveryError,
    SMTPProvider,
    UncertainEmailDeliveryError,
)


class SMTPBoundaryRegressionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.message = EmailMessage("Subject", ("to@example.com",), text_body="Body")

    def make_client(self):
        # Retain real SMTP __enter__, __exit__, and quit behavior without
        # creating a socket or resolving a hostname.
        client = object.__new__(smtplib.SMTP)
        client.send_message = MagicMock(return_value={})
        client.docmd = MagicMock(return_value=(221, b"bye"))
        client.close = MagicMock()
        return client

    def send(self, client, **kwargs):
        with patch("apps.core.services.email.smtp.smtplib.SMTP", return_value=client):
            return SMTPProvider(host="smtp.example.com", port=25, from_email="from@example.com", use_tls=False).send(
                self.message, **kwargs
            )

    def test_real_ssl_constructor_requires_a_trusted_matching_certificate(self):
        contexts = []

        class OfflineSSL(smtplib.SMTP_SSL):
            def send_message(self, *args, **kwargs):
                contexts.append(self.context)
                return {}

            def docmd(self, cmd, args=""):
                return (221, b"bye")

            def close(self):
                pass

        # Exercise SMTP_SSL's real constructor; only skip the base class's
        # network setup. Its insecure default context made this test fail.
        with (
            patch.object(smtplib.SMTP, "__init__", return_value=None),
            patch("apps.core.services.email.smtp.smtplib.SMTP_SSL", OfflineSSL),
        ):
            result = SMTPProvider(
                host="smtp.example.com",
                port=465,
                from_email="from@example.com",
                use_tls=False,
                use_ssl=True,
            ).send(self.message)

        self.assertTrue(result.accepted)
        self.assertEqual(len(contexts), 1)
        self.assertTrue(contexts[0].check_hostname)
        self.assertEqual(contexts[0].verify_mode, ssl.CERT_REQUIRED)

    def test_accepted_send_survives_quit_rejection_or_connection_failure(self):
        cases = [
            (421, b"service shutting down"),
            (550, b"QUIT rejected"),
            smtplib.SMTPServerDisconnected("closed"),
            TimeoutError("timeout"),
            RuntimeError("unexpected cleanup failure"),
        ]
        for quit_result in cases:
            with self.subTest(quit_result=quit_result):
                client = self.make_client()
                if isinstance(quit_result, Exception):
                    client.docmd.side_effect = quit_result
                else:
                    client.docmd.return_value = quit_result

                result = self.send(client)

                self.assertTrue(result.accepted)
                client.send_message.assert_called_once()
                client.docmd.assert_called_once_with("quit")
                client.close.assert_called()

    def test_accepted_send_survives_socket_close_failure(self):
        client = self.make_client()
        client.close.side_effect = OSError("close failed")

        self.assertTrue(self.send(client).accepted)
        client.send_message.assert_called_once()

    def test_partial_acceptance_stays_uncertain_when_quit_is_rejected(self):
        self.message = EmailMessage("Subject", ("to@example.com", "other@example.com"), text_body="Body")
        client = self.make_client()
        client.send_message.return_value = {"other@example.com": (550, b"rejected")}
        client.docmd.return_value = (421, b"service shutting down")

        with self.assertRaisesRegex(UncertainEmailDeliveryError, "only some recipients"):
            self.send(client)

    def test_submission_rejection_is_preserved_when_quit_is_rejected(self):
        client = self.make_client()
        client.send_message.side_effect = smtplib.SMTPDataError(554, b"message rejected")
        client.docmd.return_value = (421, b"service shutting down")

        with self.assertRaisesRegex(PermanentEmailDeliveryError, "rejected the message"):
            self.send(client)

    def test_callback_errors_are_preserved_without_submitting(self):
        for callback_error in (
            RuntimeError("claim lost"),
            OSError("callback failed"),
            smtplib.SMTPResponseException(450, b"callback failed"),
        ):
            with self.subTest(callback_error=callback_error):
                client = self.make_client()
                client.docmd.return_value = (421, b"service shutting down")

                with self.assertRaises(type(callback_error)) as caught:
                    self.send(client, before_provider_call=MagicMock(side_effect=callback_error))

                self.assertIs(caught.exception, callback_error)
                client.send_message.assert_not_called()
                client.close.assert_called()
