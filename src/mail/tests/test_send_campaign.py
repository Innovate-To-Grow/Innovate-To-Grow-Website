"""Unit tests for the SES sender in mail.services.send_campaign.

Focuses on the behaviors changed for async event tracking: capturing the
MessageId returned by boto3, passing ConfigurationSetName through to SES
only when set, and the structured SesSendResult return type.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from mail.services.send_campaign import SesSendResult, _send_via_ses


class SendViaSesTests(TestCase):
    def _client(self, message_id="SES-123"):
        client = MagicMock()
        client.send_raw_email.return_value = {"MessageId": message_id, "ResponseMetadata": {}}
        return client

    def test_returns_message_id_on_success(self):
        client = self._client("SES-ABC")
        result = _send_via_ses(
            ses_client=client,
            source="I2G <i2g@example.com>",
            recipient="target@example.com",
            subject="Hi",
            html_body="<p>Hi</p>",
        )
        self.assertIsInstance(result, SesSendResult)
        self.assertEqual(result.message_id, "SES-ABC")
        self.assertEqual(result.error, "")

    def test_configuration_set_is_passed_when_provided(self):
        client = self._client()
        _send_via_ses(
            ses_client=client,
            source="src",
            recipient="r@example.com",
            subject="S",
            html_body="B",
            configuration_set="i2g-production",
        )
        kwargs = client.send_raw_email.call_args.kwargs
        self.assertEqual(kwargs["ConfigurationSetName"], "i2g-production")

    def test_configuration_set_kwarg_is_omitted_when_empty(self):
        """SES rejects an empty-string ConfigurationSetName — must not send the kwarg at all."""
        client = self._client()
        _send_via_ses(
            ses_client=client,
            source="src",
            recipient="r@example.com",
            subject="S",
            html_body="B",
            configuration_set="",
        )
        kwargs = client.send_raw_email.call_args.kwargs
        self.assertNotIn("ConfigurationSetName", kwargs)

    def test_exception_is_caught_and_returned_as_error(self):
        client = MagicMock()
        client.send_raw_email.side_effect = RuntimeError("boom")
        result = _send_via_ses(
            ses_client=client,
            source="src",
            recipient="r@example.com",
            subject="S",
            html_body="B",
        )
        self.assertEqual(result.message_id, "")
        self.assertIn("boom", result.error)
