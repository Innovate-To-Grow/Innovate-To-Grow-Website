"""Password reset and password change serializers."""

from __future__ import annotations

from rest_framework import serializers

from authn.serializers.helpers import decrypt_password_pair
from authn.services import (
    AuthChallengeInvalid,
    consume_verification_token,
    delete_member_account,
    get_member_auth_emails,
    issue_email_challenge,
    mark_challenge_verified,
    resolve_auth_email,
    verify_email_code,
)

from .base import PURPOSE, BaseCodeVerifySerializer, BaseEmailSerializer


class PasswordResetRequestSerializer(BaseEmailSerializer):
    def save(self):
        resolved = resolve_auth_email(self.validated_data["email"], require_active=True)
        if resolved is not None:
            issue_email_challenge(
                member=resolved.member,
                purpose=PURPOSE.PASSWORD_RESET,
                target_email=resolved.delivery_email,
            )
        return {"message": "If an eligible account exists, a verification code has been sent."}


class PasswordResetVerifySerializer(BaseCodeVerifySerializer):
    purpose = PURPOSE.PASSWORD_RESET

    def save(self):
        challenge = self.validated_data["challenge"]
        return {
            "message": "Verification code accepted.",
            "verification_token": mark_challenge_verified(challenge),
        }


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    verification_token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)
    key_id = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        return BaseEmailSerializer().validate_email(value)

    def validate(self, attrs: dict) -> dict:
        resolved = resolve_auth_email(attrs["email"], require_active=True)
        if resolved is None:
            raise serializers.ValidationError({"email": "No eligible account found for this email."})
        attrs["resolved_member"] = resolved.member
        attrs["decrypted_new_password"] = decrypt_password_pair(attrs, user=resolved.member)
        return attrs

    def save(self):
        challenge = consume_verification_token(
            purpose=PURPOSE.PASSWORD_RESET,
            verification_token=self.validated_data["verification_token"],
            member=self.validated_data["resolved_member"],
        )
        member = challenge.member
        member.set_password(self.validated_data["decrypted_new_password"])
        member.save(update_fields=["password"])
        return {"message": "Password reset successfully."}


class ChangePasswordCodeRequestSerializer(BaseEmailSerializer):
    def validate_email(self, value: str) -> str:
        email = super().validate_email(value)
        eligible = set(get_member_auth_emails(self.context["request"].user))
        if email not in eligible:
            raise serializers.ValidationError("This email is not eligible for password change verification.")
        return email

    def save(self):
        issue_email_challenge(
            member=self.context["request"].user,
            purpose=PURPOSE.PASSWORD_CHANGE,
            target_email=self.validated_data["email"],
        )
        return {"message": "Verification code sent."}


class ChangePasswordCodeVerifySerializer(BaseCodeVerifySerializer):
    purpose = PURPOSE.PASSWORD_CHANGE

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        if attrs["member"] != self.context["request"].user:
            raise serializers.ValidationError({"detail": "Verification code is invalid or has expired."})
        return attrs

    def save(self):
        challenge = self.validated_data["challenge"]
        return {
            "message": "Verification code accepted.",
            "verification_token": mark_challenge_verified(challenge),
        }


class ChangePasswordCodeConfirmSerializer(serializers.Serializer):
    verification_token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)
    key_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        attrs["decrypted_new_password"] = decrypt_password_pair(attrs, user=self.context["request"].user)
        return attrs

    def save(self):
        member = self.context["request"].user
        consume_verification_token(
            purpose=PURPOSE.PASSWORD_CHANGE,
            verification_token=self.validated_data["verification_token"],
            member=member,
        )
        member.set_password(self.validated_data["decrypted_new_password"])
        member.save(update_fields=["password"])
        return {"message": "Password changed successfully."}


class DeleteAccountCodeRequestSerializer(serializers.Serializer):
    def save(self):
        member = self.context["request"].user
        email = member.get_primary_email()
        if not email:
            raise serializers.ValidationError({"detail": "No primary email is available for account deletion."})

        issue_email_challenge(
            member=member,
            purpose=PURPOSE.ACCOUNT_DELETE,
            target_email=email,
        )
        return {"message": "Deletion verification code sent."}


class DeleteAccountCodeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_code(self, value: str) -> str:
        return BaseCodeVerifySerializer().validate_code(value)

    def validate(self, attrs: dict) -> dict:
        member = self.context["request"].user
        email = member.get_primary_email()
        if not email:
            raise serializers.ValidationError({"detail": "No primary email is available for account deletion."})

        try:
            challenge = verify_email_code(
                purpose=PURPOSE.ACCOUNT_DELETE,
                target_email=email,
                code=attrs["code"],
            )
        except AuthChallengeInvalid as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        if challenge.member != member:
            raise serializers.ValidationError({"detail": "Verification code is invalid or has expired."})

        attrs["challenge"] = challenge
        return attrs

    def save(self):
        challenge = self.validated_data["challenge"]
        return {
            "message": "Deletion verification code accepted.",
            "verification_token": mark_challenge_verified(challenge),
        }


class DeleteAccountCodeConfirmSerializer(serializers.Serializer):
    verification_token = serializers.CharField(required=True)

    def save(self):
        member = self.context["request"].user
        consume_verification_token(
            purpose=PURPOSE.ACCOUNT_DELETE,
            verification_token=self.validated_data["verification_token"],
            member=member,
        )
        delete_member_account(member=member)
        return {"message": "Account deleted successfully."}
