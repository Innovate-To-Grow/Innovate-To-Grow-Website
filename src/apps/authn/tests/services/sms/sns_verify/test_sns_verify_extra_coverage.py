from datetime import timedelta
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge, SendQuotaWindow
from apps.authn.services.sms.sns_verify import (
    MAX_VERIFY_ATTEMPTS,
    PhoneVerificationDeliveryError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    _random_code,
    check_phone_verification,
    publish_plain_sms,
    start_phone_verification,
)
from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.credentials import AwsCredentialsError


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SnsVerifyExtraCoverageTest(TestCase):
    phone = "+12065551234"

    def setUp(self):
        cache.clear()
        AWSCredentialConfig.objects.all().delete()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
        )

    def test_random_code_is_six_digit_string(self):
        code = _random_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.core.services.aws.sms_send.resolve_aws_credentials")
    def test_missing_credentials_raise_a_permanent_delivery_error(self, mock_resolve, mock_boto_client):
        mock_resolve.side_effect = AwsCredentialsError("missing")
        with self.assertRaises(PhoneVerificationDeliveryError) as caught:
            publish_plain_sms(phone_number=self.phone, message="hello")
        self.assertEqual(
            (str(caught.exception), caught.exception.outcome), ("AWS credentials are not configured.", "permanent")
        )
        mock_boto_client.assert_not_called()

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_publish_maps_botocore_error_to_delivery_error(self, _mock_code, mock_boto_client):
        from botocore.exceptions import BotoCoreError

        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = BotoCoreError()
        mock_boto_client.return_value = mock_client

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_publish_maps_unknown_client_error_to_delivery_error(self, _mock_code, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = ClientError(
            {"Error": {"Code": "SomethingElse", "Message": "boom"}},
            "SendTextMessage",
        )
        mock_boto_client.return_value = mock_client

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)

    @patch("apps.core.services.aws.sms_send.boto3.client")
    def test_start_phone_verification_raises_on_invalid_template(self, mock_boto_client):
        self.aws_config.sms_message_template = "No placeholder here"
        self.aws_config.save(update_fields=["sms_message_template"])

        with self.assertRaises(PhoneVerificationDeliveryError) as caught:
            start_phone_verification(self.phone)

        # Found before anything is reserved: no code is stored, so neither the number's hourly cap nor the SMS
        # daily budget is charged for an SMS that could never be sent.
        self.assertEqual(caught.exception.outcome, "permanent")
        self.assertFalse(PhoneVerificationChallenge.objects.filter(phone_number=self.phone).exists())
        self.assertFalse(SendQuotaWindow.objects.exists())
        mock_boto_client.assert_not_called()

    def test_check_phone_verification_no_payload_raises_invalid(self):
        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(self.phone, "123456")

    def test_check_phone_verification_already_at_max_attempts_throttles(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password("123456"),
            attempts=MAX_VERIFY_ATTEMPTS,
            max_attempts=MAX_VERIFY_ATTEMPTS,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        with self.assertRaises(PhoneVerificationThrottled):
            check_phone_verification(None, "123456", challenge_id=challenge.pk)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.EXPIRED)

    @patch("apps.core.services.aws.sms_send.boto3.client")
    def test_publish_plain_sms_sends_message(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_text_message.return_value = {"MessageId": "plain-1"}
        mock_boto_client.return_value = mock_client

        message_id = publish_plain_sms(phone_number=self.phone, message="hello")

        self.assertEqual(message_id, "plain-1")
        mock_client.send_text_message.assert_called_once()

    @patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
    def test_publish_plain_sms_raises_when_not_configured(self, _mock_available):
        self.aws_config.sms_from_number = ""
        self.aws_config.save(update_fields=["sms_from_number"])

        with self.assertRaises(PhoneVerificationDeliveryError):
            publish_plain_sms(phone_number=self.phone, message="hello")
