"""
Serializers for contact phone management.
"""

import re

from rest_framework import serializers

from authn.models.contact.phone_regions import PHONE_REGION_CHOICES

_VALID_REGION_CODES = {code for code, _ in PHONE_REGION_CHOICES}


class ContactPhoneSerializer(serializers.Serializer):
    """Read-only serializer for contact phone list/detail responses."""

    id = serializers.UUIDField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    region = serializers.CharField(read_only=True)
    region_display = serializers.SerializerMethodField()
    subscribe = serializers.BooleanField(read_only=True)
    verified = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    # noinspection PyMethodMayBeStatic
    def get_region_display(self, obj) -> str:
        return obj.get_region_display_name()


class ContactPhoneCreateSerializer(serializers.Serializer):
    """Serializer for creating a new contact phone."""

    phone_number = serializers.CharField(required=True)
    region = serializers.ChoiceField(choices=PHONE_REGION_CHOICES, required=True)
    subscribe = serializers.BooleanField(default=False)

    # noinspection PyMethodMayBeStatic
    def validate_phone_number(self, value):
        # Strip whitespace and common formatting characters
        cleaned = re.sub(r"[\s()\-.]", "", value.strip())

        if not cleaned:
            raise serializers.ValidationError("Phone number is required.")

        # If it starts with +, validate digits after +
        if cleaned.startswith("+"):
            digits = cleaned[1:]
        else:
            digits = cleaned

        if not digits.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits (and an optional leading +).")

        if len(digits) < 7:
            raise serializers.ValidationError("Phone number is too short (minimum 7 digits).")

        if len(digits) > 15:
            raise serializers.ValidationError("Phone number is too long (maximum 15 digits).")

        # Store the cleaned value (normalization to E.164 happens in the service layer)
        return cleaned

    # noinspection PyMethodMayBeStatic
    def validate_region(self, value):
        if value not in _VALID_REGION_CODES:
            raise serializers.ValidationError("Invalid region.")
        return value


class ContactPhoneUpdateSerializer(serializers.Serializer):
    """Serializer for updating a contact phone (subscribe only)."""

    subscribe = serializers.BooleanField(required=True)


class ContactPhoneVerifyCodeSerializer(serializers.Serializer):
    """Serializer for verifying a contact phone with a 6-digit code."""

    code = serializers.CharField(required=True, min_length=6, max_length=6)

    # noinspection PyMethodMayBeStatic
    def validate_code(self, value):
        cleaned = value.strip()
        if not re.match(r"^\d{6}$", cleaned):
            raise serializers.ValidationError("Code must be exactly 6 digits.")
        return cleaned
