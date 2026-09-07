"""Protect OTP state across the real SES/SMTP adapters with mocked network clients."""

import smtplib
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from botocore.exceptions import ClientError, ReadTimeoutError
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import Member, SendVerificationRequest
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import issue_email_challenge, verify_email_code
from apps.authn.tests.services.test_send_verification_concurrency import send, verified_request


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
)
class ProtectedEmailTransportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(is_active=True, is_staff=True)

    def exercise(self, provider, *, send_error=None, connect_error=None, quit_error=None, expected_status):
        config = SimpleNamespace(
            is_active=True,
            delivery_configured=True,
            provider=provider,
            from_email="sender@example.com",
            from_name="Verification",
        )
        smtp_config = SimpleNamespace(
            is_configured=True,
            host="smtp.example.com",
            port=25,
            username="",
            password="",
            use_tls=False,
            use_ssl=False,
            timeout=5,
        )
        request = verified_request()

        def perform():
            issue_email_challenge(member=self.member, purpose="admin_login", target_email="member@example.com")
            return {"message": "sent"}

        with ExitStack() as stack:
            stack.enter_context(patch("apps.authn.services.email.send_email._load_config", return_value=config))
            stack.enter_context(patch("apps.authn.services.email.challenges._random_code", return_value="123456"))
            stack.enter_context(patch("apps.core.models.SMTPProviderConfig.load", return_value=smtp_config))
            stack.enter_context(
                patch(
                    "apps.core.services.email.ses.resolve_aws_credentials",
                    return_value=SimpleNamespace(
                        region="us-west-2", access_key_id="test-key", secret_access_key="test-secret"
                    ),
                )
            )
            smtp = stack.enter_context(patch("apps.core.services.email.smtp.smtplib.SMTP"))
            ses = stack.enter_context(patch("apps.core.services.email.ses.boto3.client"))
            if provider == "smtp":
                smtp.side_effect = connect_error
                client = smtp.return_value.__enter__.return_value
                delivery = client.send_message
                delivery.return_value = {}
                smtp.return_value.__exit__.side_effect = quit_error
            else:
                delivery = ses.return_value.send_raw_email
                delivery.return_value = {"MessageId": "accepted-message"}
            delivery.side_effect = send_error
            first = send(request, perform)
            replay = send(request, perform)
            self.assertEqual(first.status_code, expected_status, first.data)
            self.assertEqual(first.data, replay.data)
            self.assertEqual(delivery.call_count, 0 if connect_error else 1)
            if provider == "smtp":
                smtp.assert_called_once()
                ses.assert_not_called()
            else:
                ses.assert_called_once()
                self.assertEqual(ses.call_args.kwargs["config"].retries["total_max_attempts"], 1)
                smtp.assert_not_called()

        record = SendVerificationRequest.objects.get()
        self.assertTrue(record.quota_reserved)
        if expected_status in {202, 409}:
            otp = EmailAuthChallenge.objects.get(pk=record.otp_challenge_id)
            self.assertEqual(otp.status, "pending")
            verified = verify_email_code(purpose="admin_login", target_email="member@example.com", code="123456")
            self.assertEqual(verified.pk, otp.pk)
        else:
            self.assertFalse(EmailAuthChallenge.objects.exists())
        self.assertEqual(
            record.status, {202: "provider_accepted", 409: "unknown", 503: "definitely_failed"}[expected_status]
        )

    def test_smtp_disconnect_during_submission_preserves_otp_without_retry(self):
        self.exercise("smtp", send_error=smtplib.SMTPServerDisconnected("lost response"), expected_status=409)

    def test_smtp_message_rejection_invalidates_otp_without_retry(self):
        self.exercise("smtp", send_error=smtplib.SMTPDataError(550, b"rejected"), expected_status=503)

    def test_smtp_connection_failure_is_definite_without_retry(self):
        self.exercise("smtp", connect_error=TimeoutError("unreachable"), expected_status=503)

    def test_smtp_accepted_message_survives_quit_failure(self):
        self.exercise("smtp", quit_error=smtplib.SMTPResponseException(500, b"QUIT failed"), expected_status=202)

    def test_ses_timeout_preserves_otp_with_sdk_retries_disabled(self):
        self.exercise("ses", send_error=ReadTimeoutError(endpoint_url="https://ses.example.com"), expected_status=409)

    def test_ses_rejection_invalidates_otp_without_retry(self):
        self.exercise(
            "ses",
            send_error=ClientError(
                {"Error": {"Code": "MessageRejected"}, "ResponseMetadata": {"HTTPStatusCode": 400}},
                "SendRawEmail",
            ),
            expected_status=503,
        )
