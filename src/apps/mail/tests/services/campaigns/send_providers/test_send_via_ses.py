from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from apps.core.services.email import (
    DeliveryResult,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.mail.services.campaign.send.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_TRANSIENT,
    SES_OUTCOME_UNCERTAIN,
    SesSendResult,
    _send_via_ses,
)


class SendViaSesTests(TestCase):
    def _send(self, side_effect=None, result=None, **overrides):
        config = MagicMock(provider="ses")
        with patch("apps.mail.services.campaign.send.transport.deliver_email") as deliver:
            deliver.side_effect = side_effect
            deliver.return_value = result or DeliveryResult(provider="ses", message_id="SES-1")
            send_result = _send_via_ses(
                ses_client=config,
                source="from@example.com",
                recipient="to@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                **overrides,
            )
        return send_result, deliver

    def test_success_returns_message_id(self):
        result, deliver = self._send(
            unsubscribe_url="https://example.com/u",
            configuration_set="cfg",
        )

        self.assertEqual(result.message_id, "SES-1")
        self.assertEqual(result.error, "")
        self.assertEqual(deliver.call_args.kwargs["configuration_set"], "cfg")
        # A campaign message without a login link keeps List-Unsubscribe, the MIME path and its Sent Items copy
        # (see docs/integrations/microsoft-graph-email.md, "Sent Items").
        self.assertIs(deliver.call_args.args[0].keep_sent_copy, True)

    def test_a_login_link_message_through_ses_keeps_list_unsubscribe(self):
        _, deliver = self._send(unsubscribe_url="https://example.com/u", keep_sent_copy=False)

        message = deliver.call_args.args[0]
        self.assertIs(message.keep_sent_copy, False)
        self.assertEqual(message.headers["List-Unsubscribe"], "<https://example.com/u>")

    def test_failure_returns_error(self):
        result, _ = self._send(side_effect=UncertainEmailDeliveryError("could not be confirmed"))

        self.assertEqual(result.outcome, SES_OUTCOME_UNCERTAIN)
        self.assertIn("could not be confirmed", result.error)
        self.assertEqual(result.message_id, "")

    def test_throttle_response_is_definitive_transient(self):
        result, _ = self._send(side_effect=TransientEmailDeliveryError("slow down"))

        self.assertEqual(result.outcome, SES_OUTCOME_TRANSIENT)

    def test_access_denied_response_is_definitive_permanent(self):
        result, _ = self._send(side_effect=PermanentEmailDeliveryError("denied"))

        self.assertEqual(result.outcome, SES_OUTCOME_PERMANENT)

    def test_endpoint_connection_failure_is_safe_to_retry(self):
        result, _ = self._send(side_effect=TransientEmailDeliveryError("endpoint unavailable"))

        self.assertEqual(result.outcome, SES_OUTCOME_TRANSIENT)

    def test_send_via_ses_omits_configuration_set_when_empty(self):
        _, deliver = self._send()
        self.assertEqual(deliver.call_args.kwargs["configuration_set"], "")

    def test_recipient_attempt_is_attached_as_ses_event_tags(self):
        recipient_id = uuid4()
        _, deliver = self._send(recipient_log_id=recipient_id, delivery_attempt=2)

        message = deliver.call_args.args[0]
        self.assertEqual(
            message.headers["X-SES-MESSAGE-TAGS"],
            f"i2g_recipient_id={recipient_id}, i2g_delivery_attempt=2",
        )

    def test_smtp_messages_do_not_include_ses_event_tags(self):
        with patch("apps.mail.services.campaign.send.transport.deliver_email") as deliver:
            deliver.return_value = DeliveryResult(provider="smtp", message_id="smtp-1")
            _send_via_ses(
                ses_client=MagicMock(provider="smtp"),
                source="from@example.com",
                recipient="to@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                recipient_log_id=uuid4(),
                delivery_attempt=1,
            )

        self.assertNotIn("X-SES-MESSAGE-TAGS", deliver.call_args.args[0].headers)


class SesSendResultTests(TestCase):
    def test_defaults(self):
        result = SesSendResult()
        self.assertEqual(result.provider, "ses")
        self.assertEqual(result.message_id, "")
        self.assertEqual(result.error, "")
        self.assertEqual(result.outcome, "success")
