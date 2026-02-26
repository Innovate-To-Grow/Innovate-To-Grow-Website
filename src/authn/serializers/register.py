"""
Registration serializer for user signup.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from authn.services import RSADecryptionError, decrypt_password, is_encrypted_password

Member = get_user_model()


class RegisterSerializer(serializers.Serializer):
    """
    Serializer for user registration.
    Requires email and password. Optionally accepts first_name, last_name, organization.
    Passwords should be RSA encrypted with the public key.
    """

    email = serializers.EmailField(
        required=True,
        help_text="Email address for registration.",
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="RSA encrypted password (base64 encoded).",
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        help_text="RSA encrypted password confirmation (base64 encoded).",
    )
    key_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Key ID used for encryption (for key rotation handling).",
    )
    first_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="User's first name.",
    )
    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="User's last name.",
    )
    organization = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Organization or company the user belongs to.",
    )

    def validate_email(self, value: str) -> str:
        """
        Check that the email is not already registered.
        """
        email_lower = value.lower()
        if Member.objects.filter(email__iexact=email_lower).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email_lower

    def validate(self, attrs: dict) -> dict:
        """
        Decrypt passwords and validate them.
        """
        key_id = attrs.get("key_id", "")
        encrypted_password = attrs["password"]
        encrypted_confirm = attrs["password_confirm"]

        # Decrypt passwords if they appear to be encrypted
        if is_encrypted_password(encrypted_password):
            try:
                password = decrypt_password(encrypted_password, key_id if key_id else None)
                password_confirm = decrypt_password(encrypted_confirm, key_id if key_id else None)
            except RSADecryptionError as e:
                raise serializers.ValidationError({"password": f"Failed to decrypt password: {e}"})
        else:
            # Allow plain passwords for development/testing (not recommended for production)
            password = encrypted_password
            password_confirm = encrypted_confirm

        # Validate password length
        if len(password) < 8:
            raise serializers.ValidationError({"password": "Password must be at least 8 characters."})

        # Validate password using Django's password validators
        try:
            validate_password(password)
        except Exception as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        # Check passwords match
        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})

        # Store decrypted password for create()
        attrs["_decrypted_password"] = password
        return attrs

    def create(self, validated_data: dict) -> Member:
        """
        Create a new user with the validated data.
        User is created as inactive until email is verified.
        """
        email = validated_data["email"]
        password = validated_data["_decrypted_password"]

        # Use email as username (or generate a unique one)
        username = email.split("@")[0]
        base_username = username
        counter = 1
        while Member.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")
        organization = validated_data.get("organization", "")

        member = Member.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,  # Inactive until email verified
        )

        if organization:
            member.organization = organization
            member.save(update_fields=["organization"])

        return member
