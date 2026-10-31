"""Protect OTP state across the real SES/SMTP/Microsoft Graph adapters with mocked network clients."""

import base64
import logging
import smtplib
from contextlib import ExitStack, contextmanager
from email import message_from_bytes, policy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, ReadTimeoutError
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import Member, SendVerificationRequest
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import issue_email_challenge, verify_email_code
from apps.authn.tests.services.send_verification.test_send_verification_concurrency import send, verified_request
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.graph_helpers import make_test_credential, private_key_lines

GRAPH_TENANT_ID = "11111111-2222-3333-4444-555555555555"
GRAPH_CLIENT_ID = "66666666-7777-8888-9999-000000000000"
GRAPH_TOKEN = "not-a-real-token"
GRAPH_TOKEN_BODY = b'{"access_token": "not-a-real-token", "expires_in": 3600}'
GRAPH_ERROR_BODY = b'{"error": {"code": "ErrorSendAsDenied", "message": "leaky detail for sender@example.com"}}'


@contextmanager
def captured_logs():
    """Every log line, with tracebacks, emitted while the block runs."""
    lines = []

    class Collector(logging.Handler):
        def emit(self, record):
            lines.append(self.format(record))

    handler = Collector(level=logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield lines
    finally:
        root.removeHandler(handler)


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
)
class ProtectedEmailTransportTests(TestCase):
    def setUp(self):
        cache.clear()
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.member = Member.objects.create_user(is_active=True, is_staff=True)

    def exercise(
        self,
        provider,
        *,
        send_error=None,
        connect_error=None,
        quit_error=None,
        graph_response=None,
        token_response=None,
        expected_status,
    ):
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
        credential = make_test_credential(tenant_id=GRAPH_TENANT_ID, client_id=GRAPH_CLIENT_ID)
        # The installed certificate, as access.credential_for reads it; its key is in the in-memory store.
        certificate = SimpleNamespace(
            x5t_s256=credential.x5t_s256,
            public_key_sha256=credential.public_key_sha256,
            store_arn=credential.key_arn,
            store_version_id=credential.key_version_id,
            usable_for=lambda config: True,
        )
        graph_config = SimpleNamespace(
            is_configured=True,
            tenant_id=GRAPH_TENANT_ID,
            client_id=GRAPH_CLIENT_ID,
            current_certificate=certificate,
            mailbox="",
            # A scope that admits the sender; the scope rules have their own tests in apps.core.
            sender_mailbox=lambda from_email: from_email.lower(),
            allows=lambda mailbox, permission: True,
        )
        request = verified_request()

        def perform():
            issue_email_challenge(member=self.member, purpose="admin_login", target_email="member@example.com")
            return {"message": "sent"}

        with ExitStack() as stack:
            logs = stack.enter_context(captured_logs())
            stack.enter_context(patch("apps.authn.services.email.send_email._load_config", return_value=config))
            stack.enter_context(patch("apps.authn.services.email.challenges._random_code", return_value="123456"))
            stack.enter_context(patch("apps.core.models.SMTPProviderConfig.load", return_value=smtp_config))
            stack.enter_context(patch("apps.core.models.MicrosoftGraphProviderConfig.load", return_value=graph_config))
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
            graph = stack.enter_context(patch("apps.core.services.email.graph.transport.post"))
            if provider == "smtp":
                smtp.side_effect = connect_error
                client = smtp.return_value
                delivery = client.send_message
                delivery.return_value = {}
                client.quit.side_effect = quit_error
            elif provider == "graph":
                # ``delivery`` is the sendMail request; the identity-platform token request is answered separately.
                delivery = Mock(return_value=graph_response or HttpResponse(202, {}, b""))

                def graph_post(host, path, body, headers, *, timeout):
                    if host == "login.microsoftonline.com":
                        return token_response or HttpResponse(200, {}, GRAPH_TOKEN_BODY)
                    return delivery(host, path, body, headers)

                graph.side_effect = graph_post
            else:
                delivery = ses.return_value.send_raw_email
                delivery.return_value = {"MessageId": "accepted-message"}
            delivery.side_effect = send_error
            first = send(request, perform)
            replay = send(request, perform)
            self.assertEqual(first.status_code, expected_status, first.data)
            self.assertEqual(first.data, replay.data)
            self.assertEqual(delivery.call_count, 0 if connect_error or token_response else 1)
            if provider == "smtp":
                smtp.assert_called_once()
                ses.assert_not_called()
                graph.assert_not_called()
            elif provider == "graph":
                self.assert_graph_submission(graph, delivery, first, logs)
                ses.assert_not_called()
                smtp.assert_not_called()
            else:
                ses.assert_called_once()
                self.assertEqual(ses.call_args.kwargs["config"].retries["total_max_attempts"], 1)
                smtp.assert_not_called()
                graph.assert_not_called()

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

    def assert_graph_submission(self, post, sendmail, response, logs):
        # One token request serves the send; the replayed request must not fetch another or resubmit the message.
        token_requests = [call for call in post.call_args_list if call.args[0] == "login.microsoftonline.com"]
        self.assertEqual(len(token_requests), 1)
        if sendmail.call_count:
            host, path, body, headers = sendmail.call_args.args
            self.assertEqual((host, path), ("graph.microsoft.com", "/v1.0/users/sender@example.com/sendMail"))
            self.assertEqual(headers["Authorization"], f"Bearer {GRAPH_TOKEN}")
            mime = message_from_bytes(base64.b64decode(body), policy=policy.default)
            self.assertEqual(str(mime["To"]), "member@example.com")
            self.assertEqual(str(mime["From"]), "Verification <sender@example.com>")
            self.assertIn("123456", mime.get_body(preferencelist=("html", "plain")).get_content())
            for line in private_key_lines():
                self.assertNotIn(line.encode(), body)
        # Neither the public answer nor any log line may carry key material, a token or Graph's response body.
        visible = "\n".join([repr(response.data), *logs])
        for leaked in (GRAPH_TOKEN, "leaky detail", *private_key_lines()):
            self.assertNotIn(leaked, visible)

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

    def test_graph_accepted_message_is_submitted_once_and_keeps_the_otp(self):
        self.exercise("graph", expected_status=202)

    def test_graph_throttling_is_definite_without_retry(self):
        throttled = HttpResponse(429, {"retry-after": "30"}, GRAPH_ERROR_BODY)

        self.exercise("graph", graph_response=throttled, expected_status=503)

    def test_graph_gateway_error_after_submission_preserves_otp_without_retry(self):
        self.exercise("graph", graph_response=HttpResponse(502, {}, GRAPH_ERROR_BODY), expected_status=409)

    def test_graph_permanent_rejection_invalidates_otp_without_retry(self):
        self.exercise("graph", graph_response=HttpResponse(403, {}, GRAPH_ERROR_BODY), expected_status=503)

    def test_graph_response_lost_after_submission_preserves_otp_without_retry(self):
        self.exercise("graph", send_error=ResponseLost(), expected_status=409)

    def test_graph_connection_failure_before_submission_is_definite_without_retry(self):
        self.exercise("graph", send_error=ConnectFailed(), expected_status=503)

    def test_graph_credential_rejection_is_definite_and_submits_nothing(self):
        rejected = HttpResponse(401, {}, b'{"error": "invalid_client", "error_codes": [7000215]}')

        self.exercise("graph", token_response=rejected, expected_status=503)
