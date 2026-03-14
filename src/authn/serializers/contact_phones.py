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

    def get_region_display(self, obj) -> str:
        return obj.get_region_display_name()


class ContactPhoneCreateSerializer(serializers.Serializer):
    """Serializer for creating a new contact phone."""

    phone_number = serializers.CharField(required=True)
    region = serializers.ChoiceField(choices=PHONE_REGION_CHOICES, required=True)
    subscribe = serializers.BooleanField(default=False)

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

    def validate_region(self, value):
        if value not in _VALID_REGION_CODES:
            raise serializers.ValidationError("Invalid region.")
        return value


class ContactPhoneUpdateSerializer(serializers.Serializer):
    """Serializer for updating a contact phone (subscribe only)."""

    subscribe = serializers.BooleanField(required=True)
