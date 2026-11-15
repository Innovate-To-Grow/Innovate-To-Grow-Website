import json
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from apps.core.models import (
    DeliveryRateState,
)
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import HttpResponse
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_SUCCESS,
    SES_OUTCOME_TRANSIENT,
    SES_OUTCOME_UNCERTAIN,
    _send_via_ses,
)
from apps.mail.tests.services.campaigns.send_providers.test_send_campaign_provider_neutral import (
    DENIED_BODY,
    GRAPH_LOGGER,
    LEAKS,
    POST,
    UNSUBSCRIBE_URL,
    FakeGraphTransport,
    create_graph_sender,
    posted_mime,
)


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

    def test_a_message_with_a_login_link_is_sent_as_json_without_a_sent_items_copy(self):
        with self.assertNoLogs("apps.core.services.email.graph", "WARNING"):
            result = self.send(
                html_body='<p><a href="https://i2g.example/login#token=abc">Sign in</a></p>', keep_sent_copy=False
            )

        self.assertEqual((result.provider, result.outcome, result.error), ("graph", SES_OUTCOME_SUCCESS, ""))
        (call,) = self.transport.sent
        self.assertEqual(call.headers["Content-Type"], "application/json")
        body = json.loads(call.body)
        self.assertIs(body["saveToSentItems"], False)
        self.assertNotIn("internetMessageHeaders", body["message"])
        self.assertIn("login#token=abc", body["message"]["body"]["content"])

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
            # A full sender mailbox stops Graph sending until space is freed: retried later, not failed for good.
            (507, {}, SES_OUTCOME_TRANSIENT),
        )
        for status, headers, outcome in cases:
            with self.subTest(status=status):
                DeliveryRateState.objects.all().delete()  # each answer on its own, not inside the last one's cooldown
                self.transport.send_response = HttpResponse(status, headers, DENIED_BODY.encode())

                with self.assertLogs(GRAPH_LOGGER, level="WARNING") as logs:
                    result = self.send()

                self.assertEqual((result.provider, result.outcome, result.message_id), ("graph", outcome, ""))
                self.assertTrue(result.error)
                for leaked in LEAKS:
                    self.assertNotIn(leaked, result.error)
                    self.assertNotIn(leaked, "\n".join(logs.output))

    def test_a_rejected_certificate_is_a_definite_failure_before_any_message_is_sent(self):
        token_body = json.dumps({"error": "invalid_client", "error_codes": [700027]})
        self.transport.token_response = HttpResponse(401, {}, token_body.encode())

        result = self.send()

        self.assertEqual((result.provider, result.outcome), ("graph", SES_OUTCOME_PERMANENT))
        self.assertIn("rejected the Graph credentials", result.error)
        for leaked in LEAKS:
            self.assertNotIn(leaked, result.error)
        self.assertEqual(self.transport.sent, [])
