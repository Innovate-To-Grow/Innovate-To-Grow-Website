"""Shared serializer building blocks for email-code flows."""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from authn.models.security import EmailAuthChallenge
from authn.services import (
    AuthChallengeInvalid,
    RSADecryptionError,
    decrypt_password,
    is_encrypted_password,
    normalize_email,
    verify_email_code,
)

_CODE_RE = re.compile(r"^\d{6}$")


def decrypt_new_passwords(attrs: dict, *, user=None) -> str:
    """Decrypt, validate, and confirm a pair of password fields."""
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


class BaseEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value: str) -> str:
        return normalize_email(value)


class BaseCodeVerifySerializer(BaseEmailSerializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    purpose: str = ""

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


PURPOSE = EmailAuthChallenge.Purpose
