from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.mail.services.inbox.reply import send_reply


class InboxReplySendSettingsTest(TestCase):
    def setUp(self):
        # The inbox account and sender lists are cached per container.
        cache.clear()
        EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            from_email="reply@example.com",
            from_name="I2G",
        )

    def test_reply_requires_ses_when_aws_is_not_configured(self):
        error = send_reply(
            to_email="recipient@example.com",
            subject="Re: Hi",
            reply_body="Hello",
            cc_email="copy@example.com",
        )

        self.assertIn("Email delivery is not configured", error)

    @patch("boto3.client")
    def test_reply_returns_error_when_ses_send_fails(self, mock_boto_client):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        mock_boto_client.return_value.send_raw_email.side_effect = RuntimeError("SES failed")

        error = send_reply(
            to_email="recipient@example.com",
            subject="Re: Hi",
            reply_body="Hello",
        )

        self.assertIn("Failed to send reply", error)
        mock_boto_client.return_value.send_raw_email.assert_called_once()
