"""Edge-case coverage for public email-code views and helpers."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.test import APITestCase

from apps.authn.constants import RECOVERY_CHANNEL_UNAVAILABLE
from apps.authn.models import EmailAuthChallenge
from apps.authn.serializers.email_code.password_change import (
    ChangePasswordCodeRequestSerializer,
    ChangePasswordCodeVerifySerializer,
)
from apps.authn.serializers.email_code.password_reset_confirm import PasswordResetConfirmSerializer
from apps.authn.services import (
    AuthChallengeDeliveryError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    NoRecoveryChannelError,
)
from apps.authn.views.shared.responses import challenge_error_response

Member = get_user_model()
PURPOSE_LOGIN = EmailAuthChallenge.Purpose.LOGIN
PURPOSE_REGISTER = EmailAuthChallenge.Purpose.REGISTER


class PasswordResetSerializerSecurityTests(APITestCase):
    @patch(
        "apps.authn.serializers.email_code.password_reset_confirm.consume_verification_token",
        side_effect=AuthChallengeInvalid("internal challenge details"),
    )
    @patch("apps.authn.serializers.email_code.password_reset_confirm.validate_password")
    def test_confirm_suppresses_internal_exception_context(self, _validate_password, _consume):
        serializer = PasswordResetConfirmSerializer()
        serializer._validated_data = {
            "decrypted_new_password": "StrongPass123!",
            "resolved_member": object(),
            "verification_token": "opaque-token",
        }

        with self.assertRaises(serializers.ValidationError) as raised:
            serializer.save()

        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)
        self.assertNotIn("internal challenge details", str(raised.exception.detail))

    @patch(
        "apps.authn.serializers.email_code.password_change.select_recovery_channel",
        side_effect=NoRecoveryChannelError("internal recovery diagnostics"),
    )
    def test_password_change_serializers_use_client_safe_recovery_error(self, _select):
        request = SimpleNamespace(user=object())
        serializer_classes = (ChangePasswordCodeRequestSerializer, ChangePasswordCodeVerifySerializer)

        for serializer_class in serializer_classes:
            with self.subTest(serializer=serializer_class.__name__):
                serializer = serializer_class(context={"request": request})
                with self.assertRaises(serializers.ValidationError) as raised:
                    serializer.validate({})

                self.assertEqual(str(raised.exception.detail["detail"]), RECOVERY_CHANNEL_UNAVAILABLE)
                self.assertIsNone(raised.exception.__cause__)
                self.assertTrue(raised.exception.__suppress_context__)
                self.assertNotIn("internal recovery diagnostics", str(raised.exception.detail))


class ChallengeErrorResponseTests(APITestCase):
    def test_throttled_returns_429(self):
        resp = challenge_error_response(AuthChallengeThrottled("slow"))
        self.assertEqual(resp.status_code, 429)

    def test_delivery_error_returns_503(self):
        resp = challenge_error_response(AuthChallengeDeliveryError("nope"))
        self.assertEqual(resp.status_code, 503)

    def test_unknown_exception_reraised(self):
        with self.assertRaises(ValueError):
            challenge_error_response(ValueError("unexpected"))
