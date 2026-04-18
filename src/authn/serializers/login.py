"""
Login serializer for user authentication.
"""

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from authn.serializers.helpers import decrypt_field
from authn.services import resolve_auth_email

Member = get_user_model()


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login with email and password.
    Password should be RSA encrypted with the public key.
    """

    email = serializers.EmailField(
        required=True,
        help_text="Email address.",
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="RSA encrypted password (base64 encoded).",
    )
    key_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Key ID used for encryption (for key rotation handling).",
    )

    # noinspection PyMethodMayBeStatic
    def validate(self, attrs: dict) -> dict:
        email = attrs.get("email", "").lower()
        key_id = attrs.get("key_id", "")

        try:
            password = decrypt_field(attrs.get("password", ""), key_id)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail}) from exc

        resolved = resolve_auth_email(email, require_active=False)
        if resolved is None:
            raise serializers.ValidationError({"non_field_errors": ["Invalid credentials."]})
        member = resolved.member

        if not member.is_active:
            raise serializers.ValidationError({"non_field_errors": ["Invalid credentials."]})

        user = authenticate(username=email, password=password)
        if user is None:
            raise serializers.ValidationError({"non_field_errors": ["Invalid credentials."]})

        attrs["user"] = user
        return attrs
