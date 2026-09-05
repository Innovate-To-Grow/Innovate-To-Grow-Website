"""Compatibility coverage for the campaign delivery adapter."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.services.email import DeliveryResult, UncertainEmailDeliveryError
from apps.mail.services.send_campaign import SesSendResult, _send_via_ses


class SendViaSesTests(TestCase):
    def _send(self, *, result=None, side_effect=None, configuration_set=""):
        config = MagicMock(provider="ses")
        with patch("apps.mail.services.send_campaign.transport.deliver_email") as deliver:
            deliver.return_value = result or DeliveryResult(provider="ses", message_id="SES-123")
            deliver.side_effect = side_effect
            send_result = _send_via_ses(
                ses_client=config,
                source="I2G <i2g@example.com>",
                recipient="target@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                configuration_set=configuration_set,
            )
        return send_result, deliver

    def test_returns_message_id_on_success(self):
        result, _ = self._send(result=DeliveryResult(provider="ses", message_id="SES-ABC"))

        self.assertIsInstance(result, SesSendResult)
        self.assertEqual(result.message_id, "SES-ABC")
        self.assertEqual(result.error, "")

    def test_configuration_set_is_forwarded(self):
        _, deliver = self._send(configuration_set="i2g-production")

        self.assertEqual(deliver.call_args.kwargs["configuration_set"], "i2g-production")

    def test_empty_configuration_set_is_forwarded_safely(self):
        _, deliver = self._send(configuration_set="")

        self.assertEqual(deliver.call_args.kwargs["configuration_set"], "")

    def test_exception_is_caught_and_returned_as_error(self):
        result, _ = self._send(side_effect=UncertainEmailDeliveryError("outcome could not be confirmed"))

        self.assertEqual(result.message_id, "")
        self.assertIn("could not be confirmed", result.error)
