from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    MAX_VERIFY_ATTEMPTS,
    PhoneVerificationDeliveryError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    _get_smsvoice_client,
    _otp_cache_key,
    _random_code,
    _send_count_cache_key,
    check_phone_verification,
    publish_plain_sms,
    start_phone_verification,
)
from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ResolveAwsCredentialsTest(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.all().delete()
        EmailServiceConfig.objects.all().delete()

    def test_returns_active_aws_credential_config(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-east-1",
        )

        creds = resolve_aws_credentials("ses")

        self.assertEqual(creds.access_key_id, "aws-key")
        self.assertEqual(creds.region, "us-east-1")

    def test_all_services_share_the_same_region(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-east-1",
        )

        self.assertEqual(resolve_aws_credentials("ses").region, "us-east-1")
        self.assertEqual(resolve_aws_credentials("sns").region, "us-east-1")
        self.assertEqual(resolve_aws_credentials("bedrock").region, "us-east-1")

    def test_raises_when_no_aws_credentials_even_if_email_exists(self):
        EmailServiceConfig.objects.create(name="Email", is_active=True)

        with self.assertRaises(AwsCredentialsError):
            resolve_aws_credentials()


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SnsVerifyServiceTest(TestCase):
    phone = "+12065551234"
    origination_number = "+12065550000"

    def setUp(self):
        cache.clear()
        AWSCredentialConfig.objects.all().delete()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-west-2",
            sms_from_number=self.origination_number,
        )

    def _mock_publish(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_text_message.return_value = {"MessageId": "msg-123"}
        mock_boto_client.return_value = mock_client
        return mock_client

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_sends_sns_message(self, _mock_code, mock_boto_client):
        mock_client = self._mock_publish(mock_boto_client)

        status = start_phone_verification(self.phone)

        self.assertEqual(status, "pending")
        mock_client.send_text_message.assert_called_once()
        send_kwargs = mock_client.send_text_message.call_args.kwargs
        self.assertEqual(send_kwargs["DestinationPhoneNumber"], self.phone)
        self.assertIn("123456", send_kwargs["MessageBody"])
        self.assertEqual(send_kwargs["MessageType"], "TRANSACTIONAL")
        self.assertEqual(send_kwargs["OriginationIdentity"], self.origination_number)

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_check_phone_verification_accepts_valid_code(self, _mock_code, mock_boto_client):
        self._mock_publish(mock_boto_client)
        start_phone_verification(self.phone)

        result = check_phone_verification(self.phone, "123456")

        self.assertEqual(result, "approved")
        self.assertIsNone(cache.get(_otp_cache_key(self.phone)))

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    def test_check_phone_verification_rejects_invalid_code(self, mock_boto_client):
        cache.set(
            _otp_cache_key(self.phone),
            {"code_hash": make_password("123456"), "attempts": 0},
            timeout=600,
        )

        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(self.phone, "000000")

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    def test_check_phone_verification_throttles_after_max_attempts(self, mock_boto_client):
        cache.set(
            _otp_cache_key(self.phone),
            {"code_hash": make_password("123456"), "attempts": MAX_VERIFY_ATTEMPTS - 1},
            timeout=600,
        )

        with self.assertRaises(PhoneVerificationThrottled):
            check_phone_verification(self.phone, "000000")

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_throttles_send_count(self, _mock_code, mock_boto_client):
        self._mock_publish(mock_boto_client)
        cache.set(_send_count_cache_key(self.phone), MAX_SENDS_PER_HOUR, timeout=3600)

        with self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(self.phone)

    @patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
    def test_start_phone_verification_requires_origination_number(self, _mock_available):
        self.aws_config.sms_from_number = ""
        self.aws_config.save(update_fields=["sms_from_number"])

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)

    @patch("apps.core.services.aws.sms.resolve_origination_number", return_value="+18005550000")
    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_uses_auto_resolved_origination_number(
        self, _mock_code, mock_boto_client, _mock_resolve
    ):
        self.aws_config.sms_from_number = ""
        self.aws_config.save(update_fields=["sms_from_number"])
        mock_client = self._mock_publish(mock_boto_client)

        start_phone_verification(self.phone)

        send_kwargs = mock_client.send_text_message.call_args.kwargs
        self.assertEqual(send_kwargs["OriginationIdentity"], "+18005550000")

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_maps_invalid_phone_error(self, _mock_code, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid phone"}},
            "SendTextMessage",
        )
        mock_boto_client.return_value = mock_client

        with self.assertRaises(PhoneVerificationInvalid):
            start_phone_verification(self.phone)

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_maps_throttling_error(self, _mock_code, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "SendTextMessage",
        )
        mock_boto_client.return_value = mock_client

        with self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(self.phone)

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_maps_conflict_to_delivery_error(self, _mock_code, mock_boto_client):
        # ConflictException is an origination-identity/account-state problem, not a bad recipient.
        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = ClientError(
            {"Error": {"Code": "ConflictException", "Message": "Number in conflicting state"}},
            "SendTextMessage",
        )
        mock_boto_client.return_value = mock_client

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)


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

    @patch("apps.authn.services.sms.sns_verify.resolve_aws_credentials")
    def test_get_smsvoice_client_raises_delivery_error_when_no_credentials(self, mock_resolve):
        mock_resolve.side_effect = AwsCredentialsError("missing")
        with self.assertRaises(PhoneVerificationDeliveryError):
            _get_smsvoice_client()

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_publish_maps_botocore_error_to_delivery_error(self, _mock_code, mock_boto_client):
        from botocore.exceptions import BotoCoreError

        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = BotoCoreError()
        mock_boto_client.return_value = mock_client

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
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

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
    def test_start_phone_verification_raises_on_invalid_template(self, mock_boto_client):
        self.aws_config.sms_message_template = "No placeholder here"
        self.aws_config.save(update_fields=["sms_message_template"])

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)
        # Cache entry should have been cleaned up after the template failure.
        self.assertIsNone(cache.get(_otp_cache_key(self.phone)))

    def test_check_phone_verification_no_payload_raises_invalid(self):
        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(self.phone, "123456")

    def test_check_phone_verification_already_at_max_attempts_throttles(self):
        cache.set(
            _otp_cache_key(self.phone),
            {"code_hash": make_password("123456"), "attempts": MAX_VERIFY_ATTEMPTS},
            timeout=600,
        )
        with self.assertRaises(PhoneVerificationThrottled):
            check_phone_verification(self.phone, "123456")
        # Cache cleared on throttle.
        self.assertIsNone(cache.get(_otp_cache_key(self.phone)))

    @patch("apps.authn.services.sms.sns_verify.boto3.client")
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
