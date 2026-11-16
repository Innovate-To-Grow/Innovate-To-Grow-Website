"""Password reset, steps 2 and 3: check the reset code, then set the new password."""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.authn.constants import VERIFICATION_CONFIRM_INVALID, VERIFICATION_INVALID
from apps.authn.services import (
    AuthChallengeInvalid,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    consume_verification_token,
    resolve_login_identifier,
    verify_email_code_and_mint_token,
    verify_sms_password_code_and_mint,
)

from ..shared.encrypted_passwords import decrypt_password_pair
from .base import PURPOSE
from .password_reset_request import _identifier_value


class PasswordResetVerifySerializer(serializers.Serializer):
    """Verify a password-reset code (email or SMS) and mint a verification token."""

    identifier = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    code = serializers.CharField(required=True, min_length=6, max_length=6)
    challenge_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict) -> dict:
        resolved = resolve_login_identifier(_identifier_value(attrs), require_active=True)
        if resolved is None:
            raise serializers.ValidationError({"detail": VERIFICATION_INVALID})

        # New protected resets expose the stable send request UUID from the
        # first response onward. Resolve it to the durable OTP after dispatch;
        # old clients may continue supplying the actual phone challenge UUID.
        if attrs.get("challenge_id"):
            from apps.authn.models import SendVerificationRequest
            from apps.authn.services.send_verification.rules.constants import OP_PASSWORD_RESET_REQUEST_CODE

            record = SendVerificationRequest.objects.filter(request_id=attrs["challenge_id"]).first()
            if record is not None:
                destination = resolved.e164 if resolved.via == "phone" else resolved.email
                if (
                    record.operation != OP_PASSWORD_RESET_REQUEST_CODE
                    or record.destination_normalized != destination
                    or not record.otp_challenge_id
                ):
                    raise serializers.ValidationError({"detail": VERIFICATION_INVALID})
                attrs["challenge_id"] = record.otp_challenge_id

        if resolved.via == "email":
            try:
                _, attrs["verification_token"] = verify_email_code_and_mint_token(
                    purpose=PURPOSE.PASSWORD_RESET,
                    target_email=resolved.email,
                    code=attrs["code"],
                    member=resolved.member,
                )
            except AuthChallengeInvalid:
                raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from None
        else:
            try:
                attrs["verification_token"] = verify_sms_password_code_and_mint(
                    member=resolved.member,
                    purpose=PURPOSE.PASSWORD_RESET,
                    e164=resolved.e164,
                    code=attrs["code"],
                    challenge_id=attrs.get("challenge_id"),
                )
            except (PhoneVerificationInvalid, PhoneVerificationThrottled):
                raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from None
        return attrs

    def save(self):
        return {
            "message": "Verification code accepted.",
            "verification_token": self.validated_data["verification_token"],
        }


class PasswordResetConfirmSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    verification_token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)
    key_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        resolved = resolve_login_identifier(_identifier_value(attrs), require_active=True)
        if resolved is None:
            raise serializers.ValidationError({"detail": VERIFICATION_CONFIRM_INVALID})
        attrs["resolved_member"] = resolved.member
        attrs["decrypted_new_password"] = decrypt_password_pair(attrs, user=resolved.member)
        return attrs

    def save(self):
        new_password = self.validated_data["decrypted_new_password"]
        resolved_member = self.validated_data["resolved_member"]
        validate_password(new_password, user=resolved_member)
        try:
            challenge = consume_verification_token(
                purpose=PURPOSE.PASSWORD_RESET,
                verification_token=self.validated_data["verification_token"],
                member=resolved_member,
            )
        except AuthChallengeInvalid:
            raise serializers.ValidationError({"detail": VERIFICATION_CONFIRM_INVALID}) from None
        member = challenge.member
        member.set_password(new_password)
        member.save(update_fields=["password"])
        return {"message": "Password reset successfully."}
