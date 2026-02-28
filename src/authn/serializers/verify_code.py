"""
Serializer for code-based email verification during registration.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

Member = get_user_model()


class VerifyEmailCodeSerializer(serializers.Serializer):
    """Validates email + code for registration email verification."""

    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)

    def validate_email(self, value):
        email = value.lower().strip()
        try:
            member = Member.all_objects.get(email__iexact=email)
        except Member.DoesNotExist:
            raise serializers.ValidationError("No account found with this email.")
        self._member = member
        return email

    def validate(self, attrs):
        attrs["member"] = self._member
        return attrs
