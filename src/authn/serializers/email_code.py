"""
Serializers for email-code auth flows.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from authn.models.security import EmailAuthChallenge
from authn.services import (
    AuthChallengeInvalid,
    RSADecryptionError,
    consume_verification_token,
    decrypt_password,
    get_member_auth_emails,
    is_encrypted_password,
    issue_email_challenge,
    mark_challenge_verified,
    normalize_email,
    registration_email_conflicts,
    resolve_auth_email,
    verify_email_code,
    verify_email_code_for_purposes,
)
from authn.utils import generate_unique_username

Member = get_user_model()

_CODE_RE = re.compile(r"^\d{6}$")


def _decrypt_new_passwords(attrs: dict, *, user=None) -> str:
    key_id = attrs.get("key_id", "")
    encrypted_new = attrs["new_password"]
    encrypted_confirm = attrs["new_password_confirm"]

    if is_encrypted_password(encrypted_new):
        try:
            new_password = decrypt_password(encrypted_new, key_id if key_id else None)
            confirm_password = decrypt_password(encrypted_confirm, key_id if key_id else None)
        except RSADecryptionError as exc:
            raise serializers.ValidationError({"new_password": f"Failed to decrypt password: {exc}"}) from exc
    else:
        # Block plaintext passwords in production
        if getattr(settings, "REQUIRE_ENCRYPTED_PASSWORDS", False):
            raise serializers.ValidationError({"new_password": "Encrypted password required."})
        new_password = encrypted_new
        confirm_password = encrypted_confirm

    if len(new_password) < 8:
        raise serializers.ValidationError({"new_password": "Password must be at least 8 characters."})

    try:
        validate_password(new_password, user=user)
    except Exception as exc:  # noqa: BLE001
        raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc

    if new_password != confirm_password:
        raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})

    return new_password


def _generate_unique_username(email: str) -> str:
    return generate_unique_username(email)


class BaseEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value: str) -> str:
        return normalize_email(value)


class BaseCodeVerifySerializer(BaseEmailSerializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    purpose: str = ""

    # noinspection PyMethodMayBeStatic
    def validate_code(self, value: str) -> str:
        normalized = value.strip()
        if not _CODE_RE.match(normalized):
            raise serializers.ValidationError("Code must be a 6-digit number.")
        return normalized

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        try:
            challenge = verify_email_code(
                purpose=self.purpose,
                target_email=attrs["email"],
                code=attrs["code"],
            )
        except AuthChallengeInvalid as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        attrs["challenge"] = challenge
        attrs["member"] = challenge.member
        return attrs


class LoginCodeRequestSerializer(BaseEmailSerializer):
    def save(self):
        resolved = resolve_auth_email(self.validated_data["email"], require_active=True)
        if resolved is not None:
            issue_email_challenge(
                member=resolved.member,
                purpose=EmailAuthChallenge.Purpose.LOGIN,
                target_email=resolved.delivery_email,
            )
        return {"message": "If an eligible account exists, a verification code has been sent."}


class LoginCodeVerifySerializer(BaseCodeVerifySerializer):
    purpose = EmailAuthChallenge.Purpose.LOGIN


class UnifiedEmailAuthRequestSerializer(BaseEmailSerializer):
    # noinspection PyMethodMayBeStatic
    def _create_pending_member(self, email: str) -> Member:
        member = Member(
            username=_generate_unique_username(email),
            email=email,
            is_active=False,
            first_name="",
            last_name="",
            organization="",
        )
        member.set_unusable_password()
        member.save()
        return member

    def save(self):
        email = self.validated_data["email"]
        resolved = resolve_auth_email(email, require_active=True)
        if resolved is not None:
            issue_email_challenge(
                member=resolved.member,
                purpose=EmailAuthChallenge.Purpose.LOGIN,
                target_email=resolved.delivery_email,
            )
            return {
                "message": "Check your email for a verification code.",
                "flow": "login",
                "next_step": "verify_code",
            }

        pending_member = Member.objects.filter(email__iexact=email, is_active=False).first()
        if registration_email_conflicts(email, exclude_member_id=pending_member.pk if pending_member else None):
            raise serializers.ValidationError({"email": "This email cannot be used for registration."})

        member = pending_member or self._create_pending_member(email)
        issue_email_challenge(
            member=member,
            purpose=EmailAuthChallenge.Purpose.REGISTER,
            target_email=email,
        )
        return {
            "message": "Check your email for a verification code.",
            "flow": "register",
            "next_step": "verify_code",
        }


class UnifiedEmailAuthVerifySerializer(BaseEmailSerializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    # noinspection PyMethodMayBeStatic
    def validate_code(self, value: str) -> str:
        normalized = value.strip()
        if not _CODE_RE.match(normalized):
            raise serializers.ValidationError("Code must be a 6-digit number.")
        return normalized

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        try:
            challenge = verify_email_code_for_purposes(
                purposes=[
                    EmailAuthChallenge.Purpose.LOGIN,
                    EmailAuthChallenge.Purpose.REGISTER,
                ],
                target_email=attrs["email"],
                code=attrs["code"],
            )
        except AuthChallengeInvalid as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        attrs["challenge"] = challenge
        attrs["flow"] = "register" if challenge.purpose == EmailAuthChallenge.Purpose.REGISTER else "login"
        return attrs


class RegisterVerifyCodeSerializer(BaseCodeVerifySerializer):
    purpose = EmailAuthChallenge.Purpose.REGISTER


class RegisterResendCodeSerializer(BaseEmailSerializer):
    def save(self):
        member = Member.objects.filter(email__iexact=self.validated_data["email"], is_active=False).first()
        if member is None:
            raise serializers.ValidationError({"email": "No pending registration was found for this email."})
        issue_email_challenge(
            member=member,
            purpose=EmailAuthChallenge.Purpose.REGISTER,
            target_email=self.validated_data["email"],
        )
        return {"message": "Verification code sent."}


class PasswordResetRequestSerializer(BaseEmailSerializer):
    def save(self):
        resolved = resolve_auth_email(self.validated_data["email"], require_active=True)
        if resolved is not None:
            issue_email_challenge(
                member=resolved.member,
                purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET,
                target_email=resolved.delivery_email,
            )
        return {"message": "If an eligible account exists, a verification code has been sent."}


class PasswordResetVerifySerializer(BaseCodeVerifySerializer):
    purpose = EmailAuthChallenge.Purpose.PASSWORD_RESET

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

    # noinspection PyMethodMayBeStatic
    def validate_email(self, value: str) -> str:
        return normalize_email(value)

    # noinspection PyMethodMayBeStatic
    def validate(self, attrs: dict) -> dict:
        # Resolve the member from email so the token is bound to a specific user
        email = attrs["email"]
        resolved = resolve_auth_email(email, require_active=True)
        if resolved is None:
            raise serializers.ValidationError({"email": "No eligible account found for this email."})
        attrs["resolved_member"] = resolved.member
        attrs["decrypted_new_password"] = _decrypt_new_passwords(attrs, user=resolved.member)
        return attrs

    def save(self):
        challenge = consume_verification_token(
            purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET,
            verification_token=self.validated_data["verification_token"],
            member=self.validated_data["resolved_member"],
        )
        member = challenge.member
        member.set_password(self.validated_data["decrypted_new_password"])
        member.save(update_fields=["password"])
        return {"message": "Password reset successfully."}


class AccountEmailsSerializer(serializers.Serializer):
    emails = serializers.ListField(child=serializers.EmailField(), read_only=True)

    # noinspection PyMethodMayBeStatic
    def to_representation(self, instance):
        return {"emails": get_member_auth_emails(instance)}


class ChangePasswordCodeRequestSerializer(BaseEmailSerializer):
    def validate_email(self, value: str) -> str:
        email = super().validate_email(value)
        request = self.context["request"]
        eligible = set(get_member_auth_emails(request.user))
        if email not in eligible:
            raise serializers.ValidationError("This email is not eligible for password change verification.")
        return email

    def save(self):
        issue_email_challenge(
            member=self.context["request"].user,
            purpose=EmailAuthChallenge.Purpose.PASSWORD_CHANGE,
            target_email=self.validated_data["email"],
        )
        return {"message": "Verification code sent."}


class ChangePasswordCodeVerifySerializer(BaseCodeVerifySerializer):
    purpose = EmailAuthChallenge.Purpose.PASSWORD_CHANGE

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
        attrs["decrypted_new_password"] = _decrypt_new_passwords(attrs, user=self.context["request"].user)
        return attrs

    def save(self):
        member = self.context["request"].user
        consume_verification_token(
            purpose=EmailAuthChallenge.Purpose.PASSWORD_CHANGE,
            verification_token=self.validated_data["verification_token"],
            member=member,
        )
        member.set_password(self.validated_data["decrypted_new_password"])
        member.save(update_fields=["password"])
        return {"message": "Password changed successfully."}
