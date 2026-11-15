from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.sms.sns_verify import (
    PhoneVerificationInvalid,
    check_phone_verification,
    consume_verified_phone_challenge,
    start_phone_verification,
)
from apps.core.models import AWSCredentialConfig


class _SnsVerifyServiceCase(TestCase):
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


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SnsVerifyServiceTest(_SnsVerifyServiceCase):
    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_sends_sns_message(self, _mock_code, mock_boto_client):
        mock_client = self._mock_publish(mock_boto_client)

        result = start_phone_verification(self.phone)

        self.assertEqual(result["status"], "pending")
        challenge = PhoneVerificationChallenge.objects.get(pk=result["challenge_id"])
        self.assertEqual(challenge.phone_number, self.phone)
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.PENDING)
        self.assertIsNotNone(challenge.send_reserved_at)
        self.assertIsNotNone(challenge.sent_at)
        mock_client.send_text_message.assert_called_once()
        send_kwargs = mock_client.send_text_message.call_args.kwargs
        self.assertEqual(send_kwargs["DestinationPhoneNumber"], self.phone)
        self.assertIn("123456", send_kwargs["MessageBody"])
        self.assertEqual(send_kwargs["MessageType"], "TRANSACTIONAL")
        self.assertEqual(send_kwargs["OriginationIdentity"], self.origination_number)

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_check_phone_verification_accepts_valid_code(self, _mock_code, mock_boto_client):
        self._mock_publish(mock_boto_client)
        started = start_phone_verification(self.phone)

        result = check_phone_verification(
            None,
            "123456",
            challenge_id=started["challenge_id"],
        )

        self.assertEqual(result.status, PhoneVerificationChallenge.Status.CONSUMED)
        self.assertEqual(result.phone_number, self.phone)

    def test_approved_callback_and_consumption_roll_back_together(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        member_model = get_user_model()
        initial_member_count = member_model.objects.count()

        def fail_after_member_creation(_challenge):
            member_model.objects.create_user(password="StrongPass123!")
            raise RuntimeError("token creation failed")

        with self.assertRaisesRegex(RuntimeError, "token creation failed"):
            check_phone_verification(
                None,
                "123456",
                challenge_id=challenge.pk,
                approved_callback=fail_after_member_creation,
            )

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.PENDING)
        self.assertEqual(member_model.objects.count(), initial_member_count)

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_verified_grant_is_consumed_once_with_matching_context(self, _mock_code, mock_boto_client):
        self._mock_publish(mock_boto_client)
        member = get_user_model().objects.create_user(password="StrongPass123!")
        context = "event-registration:event-1"
        started = start_phone_verification(
            self.phone,
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=member,
            context_identifier=context,
        )

        verified = check_phone_verification(
            self.phone,
            "123456",
            challenge_id=started["challenge_id"],
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=member,
            context_identifier=context,
            consume=False,
        )

        self.assertEqual(verified.status, PhoneVerificationChallenge.Status.VERIFIED)
        self.assertIsNotNone(verified.verified_at)
        consumed = consume_verified_phone_challenge(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=member,
            context_identifier=context,
            challenge_id=verified.pk,
        )
        self.assertEqual(consumed.status, PhoneVerificationChallenge.Status.CONSUMED)
        with self.assertRaises(PhoneVerificationInvalid):
            consume_verified_phone_challenge(
                phone_number=self.phone,
                purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
                member=member,
                context_identifier=context,
                challenge_id=verified.pk,
            )
