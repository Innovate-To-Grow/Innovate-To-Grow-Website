from datetime import timedelta
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import override_settings
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    PhoneVerificationBusy,
    PhoneVerificationDeliveryError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    check_phone_verification,
    start_phone_verification,
)
from apps.authn.tests.services.sms.sns_verify.test_sns_verify_service import _SnsVerifyServiceCase


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SnsVerifyServiceTest(_SnsVerifyServiceCase):
    def test_challenge_id_is_bound_to_member_and_context(self):
        member_model = get_user_model()
        owner = member_model.objects.create_user(password="StrongPass123!")
        other = member_model.objects.create_user(password="StrongPass123!")
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.CONTACT_PHONE_VERIFY,
            member=owner,
            context_identifier="contact-1",
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(
                self.phone,
                "123456",
                challenge_id=challenge.pk,
                purpose=PhoneVerificationChallenge.Purpose.CONTACT_PHONE_VERIFY,
                member=other,
                context_identifier="contact-1",
            )
        consumed = check_phone_verification(
            self.phone,
            "123456",
            challenge_id=challenge.pk,
            purpose=PhoneVerificationChallenge.Purpose.CONTACT_PHONE_VERIFY,
            member=owner,
            context_identifier="contact-1",
        )
        self.assertEqual(consumed.pk, challenge.pk)

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_throttles_send_count(self, _mock_code, mock_boto_client):
        self._mock_publish(mock_boto_client)
        PhoneVerificationChallenge.objects.bulk_create(
            [
                PhoneVerificationChallenge(
                    phone_number=self.phone,
                    purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
                    code_hash=make_password("123456"),
                    status=PhoneVerificationChallenge.Status.EXPIRED,
                    expires_at=timezone.now(),
                    send_reserved_at=timezone.now(),
                )
                for _index in range(MAX_SENDS_PER_HOUR)
            ]
        )

        with self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(self.phone)

    @patch(
        "apps.authn.services.sms.challenges._mark_challenge_sent",
        side_effect=RuntimeError("database unavailable after provider success"),
    )
    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_provider_success_finalization_failure_preserves_reservation_and_usable_code(
        self,
        _mock_code,
        mock_boto_client,
        _mock_finalize,
    ):
        self._mock_publish(mock_boto_client)
        PhoneVerificationChallenge.objects.bulk_create(
            [
                PhoneVerificationChallenge(
                    phone_number=self.phone,
                    purpose=PhoneVerificationChallenge.Purpose.CONTACT_PHONE_VERIFY,
                    code_hash=make_password("000000"),
                    status=PhoneVerificationChallenge.Status.EXPIRED,
                    expires_at=timezone.now(),
                    send_reserved_at=timezone.now(),
                )
                for _index in range(MAX_SENDS_PER_HOUR - 1)
            ]
        )

        started = start_phone_verification(self.phone)

        challenge = PhoneVerificationChallenge.objects.get(pk=started["challenge_id"])
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.SENDING)
        self.assertIsNotNone(challenge.send_reserved_at)
        consumed = check_phone_verification(
            self.phone,
            "123456",
            challenge_id=challenge.pk,
        )
        self.assertEqual(consumed.status, PhoneVerificationChallenge.Status.CONSUMED)
        with self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(self.phone)

    @patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
    def test_start_phone_verification_requires_origination_number(self, _mock_available):
        self.aws_config.sms_from_number = ""
        self.aws_config.save(update_fields=["sms_from_number"])

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(self.phone)

    @patch("apps.core.services.aws.sms.resolve_origination_number", return_value="+18005550000")
    @patch("apps.core.services.aws.sms_send.boto3.client")
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

    @patch("apps.core.services.aws.sms_send.boto3.client")
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

    @patch("apps.core.services.aws.sms_send.boto3.client")
    @patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456")
    def test_start_phone_verification_maps_throttling_error(self, _mock_code, mock_boto_client):
        mock_client = MagicMock()
        mock_client.send_text_message.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "SendTextMessage",
        )
        mock_boto_client.return_value = mock_client

        # AWS throttling is "SMS delivery is busy" (nothing was sent), not the per-number cap.
        with self.assertRaises(PhoneVerificationBusy) as caught:
            start_phone_verification(self.phone)
        self.assertEqual(caught.exception.outcome, "transient")
        self.assertGreaterEqual(caught.exception.retry_after, 1)
        self.assertIn("SMS delivery is busy right now", str(caught.exception))

    @patch("apps.core.services.aws.sms_send.boto3.client")
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
