from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig


class AwsSmsConfigTest(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.all().delete()

    def test_is_configured_requires_aws_sns_settings(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            sms_from_number="+12065550000",
        )
        config = AWSCredentialConfig.load()

        self.assertTrue(config.is_configured)

    @patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
    def test_sns_configured_false_when_no_number_can_be_resolved(self, _mock_available):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
        )
        config = AWSCredentialConfig.load()

        self.assertFalse(config.sns_configured)

    @patch("apps.core.services.aws.sms.origination_number_available", return_value=True)
    def test_sns_configured_true_when_number_auto_resolved(self, _mock_available):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
        )
        config = AWSCredentialConfig.load()

        self.assertTrue(config.sns_configured)

    def test_render_otp_message_uses_default_template(self):
        config = AWSCredentialConfig()
        message = config.render_sms_otp_message("654321")
        self.assertIn("654321", message)

    def test_render_otp_message_requires_code_placeholder(self):
        config = AWSCredentialConfig(sms_message_template="Hello there")
        with self.assertRaises(ValueError):
            config.render_sms_otp_message("654321")
