"""
Serializers for passwordless login via email verification code.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

Member = get_user_model()


class RequestLoginCodeSerializer(serializers.Serializer):
    """Validates email for requesting a login verification code."""

    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.lower().strip()
        try:
            member = Member.objects.get(email__iexact=email)
        except Member.DoesNotExist:
            # Use a sentinel member to avoid leaking whether the email exists;
            # the view will return a generic success message either way.
            self._member = None
            return email
        if not member.is_active:
            self._member = None
            return email
        self._member = member
        return email

    def validate(self, attrs):
        attrs["member"] = self._member
        return attrs


class VerifyLoginCodeSerializer(serializers.Serializer):
    """Validates email + code for verifying a login code."""

    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)

    def validate_email(self, value):
        email = value.lower().strip()
        try:
            member = Member.objects.get(email__iexact=email)
        except Member.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")
        if not member.is_active:
            raise serializers.ValidationError("Account is not activated.")
        self._member = member
        return email

    def validate(self, attrs):
        attrs["member"] = self._member
        return attrs
