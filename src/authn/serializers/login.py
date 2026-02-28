"""
Login serializer for user authentication.
"""

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from authn.services import RSADecryptionError, decrypt_password, is_encrypted_password

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

    def validate(self, attrs: dict) -> dict:
        """
        Validate credentials and return the authenticated user.
        """
        email = attrs.get("email", "").lower()
        encrypted_password = attrs.get("password", "")
        key_id = attrs.get("key_id", "")

        # Decrypt password if it appears to be encrypted
        if is_encrypted_password(encrypted_password):
            try:
                password = decrypt_password(encrypted_password, key_id if key_id else None)
            except RSADecryptionError as e:
                raise serializers.ValidationError({"password": f"Failed to decrypt password: {e}"})
        else:
            # Allow plain passwords for development/testing (not recommended for production)
            password = encrypted_password

        # Find user by email
        try:
            member = Member.objects.get(email__iexact=email)
        except Member.DoesNotExist:
            raise serializers.ValidationError({"non_field_errors": ["Invalid credentials."]})

        # Check if account is active
        if not member.is_active:
            raise serializers.ValidationError({"email": "Account is not activated. Please verify your email first."})

        # Authenticate using username (Django's default backend)
        user = authenticate(username=member.username, password=password)
        if user is None:
            raise serializers.ValidationError({"non_field_errors": ["Invalid credentials."]})

        attrs["user"] = user
        return attrs
