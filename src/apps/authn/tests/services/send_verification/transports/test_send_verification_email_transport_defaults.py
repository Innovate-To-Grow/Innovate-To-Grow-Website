import smtplib

from django.test import override_settings

from apps.authn.tests.services.send_verification.transports.email_transport_case import _ProtectedEmailTransportCase


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
)
class ProtectedEmailTransportTests(_ProtectedEmailTransportCase):
    def test_smtp_disconnect_during_submission_preserves_otp_without_retry(self):
        self.exercise("smtp", send_error=smtplib.SMTPServerDisconnected("lost response"), expected_status=409)
