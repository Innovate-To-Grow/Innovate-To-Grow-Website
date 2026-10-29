"""Campaign sending is provider neutral: SES-only tags and warnings never apply to Microsoft Graph or SMTP.

The real ``GraphProvider`` runs in the end-to-end cases; only ``graph.transport.post`` is replaced, so no test
touches the network and every secret below is an obviously fake value.
"""

import base64
import json
from email import message_from_bytes, policy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig, SMTPProviderConfig
from apps.core.services.aws.provider_outcomes import NO_PROVIDER_RETRIES
from apps.core.services.email import (
    DeliveryResult,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.send_campaign.runner import _configured_provider, send_campaign
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_SUCCESS,
    SES_OUTCOME_TRANSIENT,
    SES_OUTCOME_UNCERTAIN,
    SesSendResult,
    _send_via_ses,
)

# Graph senders used in this module; the mailbox scope rules have their own tests.
GRAPH_TEST_SCOPE = ("mailer@example.com", "from@example.com", "admin@example.com")

POST = "apps.core.services.email.graph.transport.post"
RUNNER_LOGGER = "apps.mail.services.send_campaign.runner"
GRAPH_LOGGER = "apps.core.services.email.graph.provider"
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "66666666-7777-8888-9999-000000000000"
CLIENT_SECRET = "not-a-real-secret"
FAKE_TOKEN = "not-a-real-token"
UNSUBSCRIBE_URL = "https://backend.example.com/mail/unsubscribe/token/"
DENIED_BODY = json.dumps({"error": {"code": "ErrorSendAsDenied", "message": "leaky detail for mailer@example.com"}})
LEAKS = (CLIENT_SECRET, FAKE_TOKEN, "leaky detail")


class FakeGraphTransport:
    """Replacement for ``graph.transport.post``: one token answer for the identity host, one for the Graph host."""

    def __init__(self, send_response=None, token_response=None):
        self.send_response = send_response or HttpResponse(202, {}, b"")
        self.token_response = token_response or HttpResponse(
            200, {}, json.dumps({"access_token": FAKE_TOKEN, "expires_in": 3600}).encode()
        )
        self.calls = []

    def __call__(self, host, path, body, headers, *, timeout):
        self.calls.append(SimpleNamespace(host=host, path=path, body=body, headers=headers))
        return self.token_response if host == "login.microsoftonline.com" else self.send_response

    @property
    def token_requests(self):
        return [call for call in self.calls if call.host == "login.microsoftonline.com"]

    @property
    def sent(self):
        return [call for call in self.calls if call.host == "graph.microsoft.com"]


def posted_mime(call):
    """The MIME message a sendMail request carried (Graph takes it base64 encoded)."""
    return message_from_bytes(base64.b64decode(call.body), policy=policy.default)


def create_graph_sender():
    create_graph_config(
        scope=GRAPH_TEST_SCOPE,
        name="Outlook Sender",
        is_active=True,
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        mailbox="mailer@example.com",
    )
    return EmailServiceConfig.objects.create(
        name="Graph sender",
        is_active=True,
        provider="graph",
        from_email="mailer@example.com",
        from_name="Innovate to Grow",
        max_send_rate=0,
    )


class SendViaGraphConfigTests(SimpleTestCase):
    """``_send_via_ses`` with a Graph configuration; the provider call itself is replaced."""

    def send(self, *, result=None, side_effect=None, **overrides):
        config = MagicMock(provider="graph")
        with patch("apps.mail.services.send_campaign.transport.deliver_email") as deliver:
            deliver.side_effect = side_effect
            deliver.return_value = result or DeliveryResult(provider="graph", message_id="<id@mailer.example.com>")
            send_result = _send_via_ses(
                ses_client=config,
                source="from@example.com",
                recipient="to@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                **overrides,
            )
        return send_result, deliver, config

    def test_graph_messages_do_not_include_ses_event_tags(self):
        _, deliver, _ = self.send(recipient_log_id=uuid4(), delivery_attempt=2)

        self.assertNotIn("X-SES-MESSAGE-TAGS", deliver.call_args.args[0].headers)

    def test_graph_messages_keep_the_one_click_unsubscribe_headers(self):
        _, deliver, _ = self.send(unsubscribe_url=UNSUBSCRIBE_URL, recipient_log_id=uuid4(), delivery_attempt=1)

        self.assertEqual(
            deliver.call_args.args[0].headers,
            {"List-Unsubscribe": f"<{UNSUBSCRIBE_URL}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
        )

    def test_graph_messages_without_an_unsubscribe_url_carry_no_extra_headers(self):
        _, deliver, _ = self.send(recipient_log_id=uuid4(), delivery_attempt=1)

        self.assertEqual(deliver.call_args.args[0].headers, {})

    def test_graph_configuration_is_passed_to_the_delivery_facade_without_provider_retries(self):
        _, deliver, config = self.send(configuration_set="ignored-set")

        self.assertIs(deliver.call_args.kwargs["config"], config)
        self.assertIs(deliver.call_args.kwargs["retry_config"], NO_PROVIDER_RETRIES)

    def test_success_reports_the_graph_provider_and_the_mime_message_id(self):
        result, _, _ = self.send()

        self.assertEqual((result.provider, result.message_id, result.error), ("graph", "<id@mailer.example.com>", ""))
        self.assertEqual(result.outcome, SES_OUTCOME_SUCCESS)

    def test_failures_keep_their_classification_and_name_the_graph_provider(self):
        cases = (
            (TransientEmailDeliveryError("throttled"), SES_OUTCOME_TRANSIENT),
            (PermanentEmailDeliveryError("rejected"), SES_OUTCOME_PERMANENT),
            (UncertainEmailDeliveryError("gateway error"), SES_OUTCOME_UNCERTAIN),
        )
        for error, outcome in cases:
            with self.subTest(outcome=outcome):
                result, _, _ = self.send(side_effect=error)

                self.assertEqual((result.provider, result.outcome, result.message_id), ("graph", outcome, ""))
                self.assertEqual(result.error, str(error))


class SendViaGraphEndToEndTests(TestCase):
    """``_send_via_ses`` through the real Graph provider and the real delivery facade."""

    def setUp(self):
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.config = create_graph_sender()
        self.transport = FakeGraphTransport()

    def send(self, **overrides):
        values = {
            "ses_client": self.config,
            "source": self.config.source_address,
            "recipient": "member@example.com",
            "subject": "Spring update",
            "html_body": "<p>Hello</p>",
            "unsubscribe_url": UNSUBSCRIBE_URL,
            "configuration_set": "tracking-set",
            "recipient_log_id": uuid4(),
            "delivery_attempt": 1,
        }
        with patch(POST, self.transport):
            return _send_via_ses(**{**values, **overrides})

    def test_sent_message_keeps_list_unsubscribe_headers_and_has_no_ses_tags(self):
        result = self.send()

        self.assertEqual((result.provider, result.outcome, result.error), ("graph", SES_OUTCOME_SUCCESS, ""))
        (call,) = self.transport.sent
        self.assertEqual((call.host, call.path), ("graph.microsoft.com", "/v1.0/users/mailer@example.com/sendMail"))
        mime = posted_mime(call)
        self.assertEqual(mime["List-Unsubscribe"], f"<{UNSUBSCRIBE_URL}>")
        self.assertEqual(mime["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertIsNone(mime["X-SES-MESSAGE-TAGS"])
        self.assertEqual((mime["To"], mime["Subject"]), ("member@example.com", "Spring update"))
        self.assertEqual(mime["From"], "Innovate to Grow <mailer@example.com>")
        self.assertEqual(result.message_id, mime["Message-ID"])

    def test_message_without_an_unsubscribe_url_has_no_list_headers(self):
        self.send(unsubscribe_url="")

        mime = posted_mime(self.transport.sent[0])
        self.assertIsNone(mime["List-Unsubscribe"])
        self.assertIsNone(mime["List-Unsubscribe-Post"])

    def test_graph_http_failures_are_classified_and_leak_no_secrets_or_response_details(self):
        cases = (
            (429, {"retry-after": "7"}, SES_OUTCOME_TRANSIENT),
            (503, {}, SES_OUTCOME_TRANSIENT),
            (401, {}, SES_OUTCOME_TRANSIENT),
            (502, {}, SES_OUTCOME_UNCERTAIN),
            (500, {}, SES_OUTCOME_UNCERTAIN),
            (403, {}, SES_OUTCOME_PERMANENT),
            (400, {}, SES_OUTCOME_PERMANENT),
            (507, {}, SES_OUTCOME_PERMANENT),
        )
        for status, headers, outcome in cases:
            with self.subTest(status=status):
                self.transport.send_response = HttpResponse(status, headers, DENIED_BODY.encode())

                with self.assertLogs(GRAPH_LOGGER, level="WARNING") as logs:
                    result = self.send()

                self.assertEqual((result.provider, result.outcome, result.message_id), ("graph", outcome, ""))
                self.assertTrue(result.error)
                for leaked in LEAKS:
                    self.assertNotIn(leaked, result.error)
                    self.assertNotIn(leaked, "\n".join(logs.output))

    def test_rejected_client_secret_is_a_definite_failure_before_any_message_is_sent(self):
        token_body = json.dumps({"error": "invalid_client", "error_codes": [7000215]})
        self.transport.token_response = HttpResponse(401, {}, token_body.encode())

        result = self.send()

        self.assertEqual((result.provider, result.outcome), ("graph", SES_OUTCOME_PERMANENT))
        self.assertIn("rejected the Graph credentials", result.error)
        self.assertNotIn(CLIENT_SECRET, result.error)
        self.assertEqual(self.transport.sent, [])


class SesTrackingWarningTests(TestCase):
    """The 'no SES configuration set' warning concerns SES bounce tracking, so only SES campaigns may log it."""

    def setUp(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key=CLIENT_SECRET,
            default_region="us-west-2",
        )
        SMTPProviderConfig.objects.create(name="SMTP", is_active=True, host="smtp.example.com", port=587)
        self.config = create_graph_sender()
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        make_member(email="alice@example.com", first_name="Alice", last_name="Smith")

    def run_campaign(self, provider):
        self.config.provider = provider
        self.config.save()
        campaign = EmailCampaign.objects.create(
            subject="Hi", body="<p>Hello</p>", audience_type="subscribers", member_email_scope="primary", status="draft"
        )
        result = SesSendResult(message_id="ID-1", provider=provider)
        with patch(f"{RUNNER_LOGGER}._send_via_ses", return_value=result):
            return send_campaign(campaign, self.sender), campaign

    @override_settings(SES_CONFIGURATION_SET_NAME="")
    def test_ses_campaign_without_a_configuration_set_warns_that_tracking_is_disabled(self):
        with self.assertLogs(RUNNER_LOGGER, level="WARNING") as logs:
            summary, campaign = self.run_campaign("ses")

        self.assertEqual(summary, {"total": 2, "sent": 2, "failed": 0})
        self.assertEqual(len(logs.records), 1)
        self.assertIn("No SES configuration set configured", logs.output[0])
        self.assertIn(str(campaign.pk), logs.output[0])

    @override_settings(SES_CONFIGURATION_SET_NAME="tracking-set")
    def test_ses_campaign_with_a_configuration_set_does_not_warn(self):
        with self.assertNoLogs(RUNNER_LOGGER, level="WARNING"):
            summary, _ = self.run_campaign("ses")

        self.assertEqual(summary["sent"], 2)

    @override_settings(SES_CONFIGURATION_SET_NAME="")
    def test_graph_and_smtp_campaigns_never_warn_about_ses_tracking(self):
        for provider in ("graph", "smtp"):
            with self.subTest(provider=provider), self.assertNoLogs(RUNNER_LOGGER, level="WARNING"):
                summary, campaign = self.run_campaign(provider)

                campaign.refresh_from_db()
                self.assertEqual((summary["sent"], campaign.status), (2, "sent"))


@override_settings(BACKEND_URL="https://backend.example.com")
class GraphCampaignRunTests(TestCase):
    """A whole ``send_campaign`` run through the real Graph provider."""

    def setUp(self):
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.config = create_graph_sender()
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        make_member(email="alice@example.com", first_name="Alice", last_name="Smith")
        make_member(email="bob@example.com", first_name="Bob", last_name="Jones")
        self.campaign = EmailCampaign.objects.create(
            subject="Hi {{first_name}}",
            body="<p>Hello</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
        )

    def logs_by_recipient(self):
        return {log.email_address: log for log in RecipientLog.objects.filter(campaign=self.campaign)}

    def test_campaign_is_delivered_through_graph_with_unsubscribe_headers_and_no_ses_tags(self):
        transport = FakeGraphTransport()

        with patch(POST, transport):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 3, "failed": 0})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sent")
        self.assertEqual(len(transport.sent), 3)
        self.assertEqual(len(transport.token_requests), 1)
        logs = self.logs_by_recipient()
        for call in transport.sent:
            mime = posted_mime(call)
            log = logs[str(mime["To"])]
            self.assertEqual(call.path, "/v1.0/users/mailer@example.com/sendMail")
            self.assertEqual((log.provider, log.status, log.error_message), ("graph", "sent", ""))
            self.assertEqual(log.provider_message_id, mime["Message-ID"])
            self.assertIsNone(mime["X-SES-MESSAGE-TAGS"])
            self.assertTrue(mime["List-Unsubscribe"].startswith("<https://backend.example.com/mail/unsubscribe/"))
            self.assertEqual(mime["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertEqual(len({log.provider_message_id for log in logs.values()}), 3)

    def test_graph_rejection_fails_every_recipient_with_a_generic_message(self):
        transport = FakeGraphTransport(HttpResponse(403, {}, DENIED_BODY.encode()))

        with self.assertLogs(GRAPH_LOGGER, level="WARNING") as captured, patch(POST, transport):
            send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.failed_count), ("failed", 3))
        for log in self.logs_by_recipient().values():
            self.assertEqual((log.provider, log.status, log.provider_message_id), ("graph", "failed", ""))
            self.assertEqual(log.error_message, "Microsoft Graph rejected the request (ErrorSendAsDenied).")
        for leaked in LEAKS:
            self.assertNotIn(leaked, "\n".join(captured.output))

    def test_throttled_recipients_fail_with_a_retryable_message_and_the_run_continues(self):
        transport = FakeGraphTransport(HttpResponse(429, {"retry-after": "30"}, DENIED_BODY.encode()))

        with self.assertLogs(GRAPH_LOGGER, level="WARNING"), patch(POST, transport):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 0, "failed": 3})
        self.assertEqual(len(transport.sent), 3)
        for log in self.logs_by_recipient().values():
            self.assertEqual(log.error_message, "Microsoft Graph temporarily rejected the request.")

    def test_graph_selected_without_active_graph_credentials_fails_before_anything_is_sent(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)
        transport = FakeGraphTransport()

        with patch(POST, transport), self.assertRaisesMessage(RuntimeError, "Email delivery is not configured"):
            send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")
        self.assertEqual(transport.calls, [])
        for log in self.logs_by_recipient().values():
            self.assertEqual((log.status, log.provider), ("failed", ""))

    def test_unexpected_errors_record_graph_as_the_configured_provider(self):
        transport = FakeGraphTransport()
        self.assertEqual(_configured_provider(self.config), "graph")

        with (
            patch(POST, transport),
            patch(f"{RUNNER_LOGGER}.personalize", side_effect=RuntimeError("boom")),
            self.assertLogs(RUNNER_LOGGER, level="ERROR"),
        ):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 0, "failed": 3})
        self.assertEqual(transport.calls, [])
        for log in self.logs_by_recipient().values():
            self.assertEqual((log.provider, log.status), ("graph", "failed"))
