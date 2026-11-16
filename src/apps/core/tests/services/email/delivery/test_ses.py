from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from django.test import SimpleTestCase

from apps.core.services.aws.credentials import AwsCredentialsError
from apps.core.services.email import (
    EmailMessage,
    PermanentEmailDeliveryError,
    SESProvider,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)


class SESTests(SimpleTestCase):
    def setUp(self):
        self.message = EmailMessage("Subject", ("to@example.com",), text_body="Body", bcc=("bcc@example.com",))
        self.credentials = SimpleNamespace(region="us-west-2", access_key_id="key", secret_access_key="secret")

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_sends_raw_message_with_explicit_credentials(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials
        client_factory.return_value.send_raw_email.return_value = {"MessageId": "ses-id"}
        provider = SESProvider(from_email="from@example.com", from_name="Name", configuration_set="events")

        result = provider.send(self.message)

        self.assertEqual(result.message_id, "ses-id")
        client_factory.assert_called_once()
        call = client_factory.call_args
        self.assertEqual(call.kwargs["aws_access_key_id"], "key")
        send = client_factory.return_value.send_raw_email.call_args.kwargs
        self.assertEqual(send["Destinations"], ["to@example.com", "bcc@example.com"])
        self.assertEqual(send["ConfigurationSetName"], "events")
        self.assertNotIn(b"Bcc:", send["RawMessage"]["Data"])

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_callback_failure_is_not_reclassified(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials

        with self.assertRaisesRegex(RuntimeError, "claim lost"):
            SESProvider(from_email="from@example.com").send(
                self.message,
                before_provider_call=MagicMock(side_effect=RuntimeError("claim lost")),
            )

        client_factory.return_value.send_raw_email.assert_not_called()

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_classifies_aws_failures(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials
        cases = [
            (EndpointConnectionError(endpoint_url="https://ses"), TransientEmailDeliveryError),
            (ReadTimeoutError(endpoint_url="https://ses", error="timeout"), UncertainEmailDeliveryError),
            (
                ClientError(
                    {"Error": {"Code": "MessageRejected"}, "ResponseMetadata": {"HTTPStatusCode": 400}}, "SendRawEmail"
                ),
                PermanentEmailDeliveryError,
            ),
        ]
        for error, expected in cases:
            client_factory.return_value.send_raw_email.side_effect = error
            with self.subTest(error=type(error).__name__), self.assertRaises(expected):
                SESProvider(from_email="from@example.com").send(self.message)

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_passes_retry_config_to_client(self, client_factory, resolve_credentials):
        from botocore.config import Config

        resolve_credentials.return_value = self.credentials
        client_factory.return_value.send_raw_email.return_value = {"MessageId": "ses-id"}
        retry = Config(retries={"max_attempts": 2})

        SESProvider(from_email="from@example.com", retry_config=retry).send(self.message)

        # The caller's retry policy, with the DELIVERY_RATES timeout of each call (botocore's own is 60 s).
        config = client_factory.call_args.kwargs["config"]
        self.assertEqual(config.retries, {"max_attempts": 2})
        self.assertEqual((config.connect_timeout, config.read_timeout), (10, 10))

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    def test_missing_credentials_are_permanent(self, resolve_credentials):
        resolve_credentials.side_effect = AwsCredentialsError("missing")

        with self.assertRaises(PermanentEmailDeliveryError):
            SESProvider(from_email="from@example.com").send(self.message)

    @patch("apps.core.services.email.ses.resolve_aws_credentials")
    @patch("apps.core.services.email.ses.boto3.client")
    def test_empty_message_id_is_uncertain(self, client_factory, resolve_credentials):
        resolve_credentials.return_value = self.credentials
        client_factory.return_value.send_raw_email.return_value = {}

        with self.assertRaises(UncertainEmailDeliveryError):
            SESProvider(from_email="from@example.com").send(self.message)
