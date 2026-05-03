"""Shared serializer building blocks for email-code flows."""

from __future__ import annotations

import re

from rest_framework import serializers

from authn.models.security import EmailAuthChallenge
from authn.security_messages import VERIFICATION_INVALID
from authn.services import AuthChallengeInvalid, normalize_email, verify_email_code

_CODE_RE = re.compile(r"^\d{6}$")


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
            raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from exc

        attrs["challenge"] = challenge
        attrs["member"] = challenge.member
        return attrs


PURPOSE = EmailAuthChallenge.Purpose
