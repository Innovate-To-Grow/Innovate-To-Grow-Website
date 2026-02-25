"""
Change password serializer for authenticated users.
"""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from authn.services import RSADecryptionError, decrypt_password, is_encrypted_password


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing an authenticated user's password.
    Passwords should be RSA encrypted with the public key.
    """

    current_password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Current password (RSA encrypted).",
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="New password (RSA encrypted).",
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        help_text="New password confirmation (RSA encrypted).",
    )
    key_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Key ID used for encryption (for key rotation handling).",
    )

    def validate(self, attrs: dict) -> dict:
        """
        Decrypt passwords and validate them.
        """
        user = self.context["request"].user
        key_id = attrs.get("key_id", "")

        encrypted_current = attrs["current_password"]
        encrypted_new = attrs["new_password"]
        encrypted_confirm = attrs["new_password_confirm"]

        # Decrypt passwords if they appear to be encrypted
        if is_encrypted_password(encrypted_current):
            try:
                current_password = decrypt_password(encrypted_current, key_id if key_id else None)
                new_password = decrypt_password(encrypted_new, key_id if key_id else None)
                new_password_confirm = decrypt_password(encrypted_confirm, key_id if key_id else None)
            except RSADecryptionError as e:
                raise serializers.ValidationError({"current_password": f"Failed to decrypt password: {e}"})
        else:
            current_password = encrypted_current
            new_password = encrypted_new
            new_password_confirm = encrypted_confirm

        # Verify current password
        if not user.check_password(current_password):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})

        # Validate new password length
        if len(new_password) < 8:
            raise serializers.ValidationError({"new_password": "Password must be at least 8 characters."})

        # Validate new password with Django's password validators
        try:
            validate_password(new_password, user=user)
        except Exception as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})

        # Check new passwords match
        if new_password != new_password_confirm:
            raise serializers.ValidationError({"new_password_confirm": "New passwords do not match."})

        attrs["_decrypted_new_password"] = new_password
        return attrs
