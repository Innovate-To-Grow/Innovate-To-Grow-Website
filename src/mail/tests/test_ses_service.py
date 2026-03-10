"""Tests for the SES mail service."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from mail.models import SESAccount
from mail.services.ses import SESService, SESServiceError


@override_settings(
    SES_AWS_ACCESS_KEY_ID="ses-access-key",
    SES_AWS_SECRET_ACCESS_KEY="ses-secret-key",
    SES_AWS_REGION="us-west-2",
)
class SESServiceTest(TestCase):
    """Tests for SESService sends and error handling."""

    def setUp(self):
        SESAccount.all_objects.all().hard_delete()
        self.account = SESAccount.objects.create(
            display_name="Innovate to Grow",
            is_active=True,
        )

    @patch("mail.services.ses.boto3.client")
    def test_send_message_success(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_raw_email.return_value = {"MessageId": "ses-msg-123"}
        mock_boto_client.return_value = mock_client

        result = SESService(self.account).send_message(
            to="student@example.com",
            subject="SES Test",
            body_html="<p>Hello <strong>SES</strong></p>",
            cc="copy@example.com",
            bcc="hidden@example.com",
            attachments=[("hello.txt", b"hello world")],
        )

        self.assertEqual(result["id"], "ses-msg-123")
        mock_boto_client.assert_called_once_with(
            "ses",
            region_name="us-west-2",
            aws_access_key_id="ses-access-key",
            aws_secret_access_key="ses-secret-key",
        )

        send_kwargs = mock_client.send_raw_email.call_args.kwargs
        self.assertEqual(send_kwargs["Destinations"], ["student@example.com", "copy@example.com", "hidden@example.com"])
        self.assertEqual(send_kwargs["Source"], "Innovate to Grow <i2g@g.ucmerced.edu>")
        raw_data = send_kwargs["RawMessage"]["Data"]
        self.assertIn(b"Subject: SES Test", raw_data)
        self.assertIn(b"hello.txt", raw_data)

    @override_settings(
        SES_AWS_ACCESS_KEY_ID="",
        SES_AWS_SECRET_ACCESS_KEY="",
    )
    def test_send_message_requires_credentials(self):
        with self.assertRaises(SESServiceError) as ctx:
            SESService(self.account).send_message(
                to="student@example.com",
                subject="Missing creds",
                body_html="<p>Hi</p>",
            )

        self.assertIn("credentials", str(ctx.exception).lower())

    @patch("mail.services.ses.boto3.client")
    def test_send_message_wraps_boto_errors(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_raw_email.side_effect = Exception("SES unavailable")
        mock_boto_client.return_value = mock_client

        with self.assertRaises(SESServiceError) as ctx:
            SESService(self.account).send_message(
                to="student@example.com",
                subject="Failure",
                body_html="<p>Hi</p>",
            )

        self.assertIn("SES unavailable", str(ctx.exception))
