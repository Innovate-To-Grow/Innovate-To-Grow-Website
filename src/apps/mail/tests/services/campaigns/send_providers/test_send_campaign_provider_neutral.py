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

from django.test import SimpleTestCase

from apps.core.models import (
    EmailServiceConfig,
)
from apps.core.services.aws.provider_outcomes import NO_PROVIDER_RETRIES
from apps.core.services.email import (
    DeliveryResult,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config, private_key_lines
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_SUCCESS,
    SES_OUTCOME_TRANSIENT,
    SES_OUTCOME_UNCERTAIN,
    _send_via_ses,
)

# Graph senders used in this module; the mailbox scope rules have their own tests.
GRAPH_TEST_SCOPE = ("mailer@example.com", "from@example.com", "admin@example.com")

POST = "apps.core.services.email.graph.transport.post"
RUNNER_LOGGER = "apps.mail.services.send_campaign.runner"
GRAPH_LOGGER = "apps.core.services.email.graph.provider"
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "66666666-7777-8888-9999-000000000000"
AWS_SECRET = "not-a-real-secret"
FAKE_TOKEN = "not-a-real-token"
UNSUBSCRIBE_URL = "https://backend.example.com/mail/unsubscribe/token/"
DENIED_BODY = json.dumps({"error": {"code": "ErrorSendAsDenied", "message": "leaky detail for mailer@example.com"}})
LEAKS = (FAKE_TOKEN, "leaky detail", *private_key_lines())


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


class ScriptedGraphTransport(FakeGraphTransport):
    """``FakeGraphTransport`` whose sendMail answers are taken in order, the last one repeating."""

    def __init__(self, *answers):
        super().__init__(answers[0])
        self.answers = list(answers)

    def __call__(self, host, path, body, headers, *, timeout):
        if host == "graph.microsoft.com":
            self.send_response = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return super().__call__(host, path, body, headers, timeout=timeout)


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

    def test_a_message_with_a_login_link_keeps_no_sent_items_copy_and_so_no_list_unsubscribe(self):
        _, deliver, _ = self.send(unsubscribe_url=UNSUBSCRIBE_URL, keep_sent_copy=False)

        message = deliver.call_args.args[0]
        self.assertIs(message.keep_sent_copy, False)
        self.assertEqual(message.headers, {})

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
