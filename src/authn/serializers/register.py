"""
Registration serializer for user signup.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from authn.models.security import EmailAuthChallenge
from authn.services import (
    RSADecryptionError,
    decrypt_password,
    is_encrypted_password,
    issue_email_challenge,
    normalize_email,
    registration_email_conflicts,
)

Member = get_user_model()

_HTML_TAG_RE = re.compile(r"<[^>]+>")


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

    # noinspection PyMethodMayBeStatic
    def validate_first_name(self, value: str) -> str:
        if _HTML_TAG_RE.search(value):
            raise serializers.ValidationError("First name must not contain HTML tags.")
        return value

    # noinspection PyMethodMayBeStatic
    def validate_last_name(self, value: str) -> str:
        if _HTML_TAG_RE.search(value):
            raise serializers.ValidationError("Last name must not contain HTML tags.")
        return value

    # noinspection PyAttributeOutsideInit
    def validate_email(self, value: str) -> str:
        """
        Check that the email is not already registered.
        """
        from authn.models import ContactEmail

        email_lower = normalize_email(value)
        pending_contact = (
            ContactEmail.objects.filter(email_address__iexact=email_lower, member__is_active=False)
            .select_related("member")
            .first()
        )
        pending_member = pending_contact.member if pending_contact else None
        if registration_email_conflicts(email_lower, exclude_member_id=pending_member.pk if pending_member else None):
            raise serializers.ValidationError("A user with this email already exists.")
        self._pending_member = pending_member
        return email_lower

    # noinspection PyMethodMayBeStatic
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
            # Block plaintext passwords in production
            if getattr(settings, "REQUIRE_ENCRYPTED_PASSWORDS", False):
                raise serializers.ValidationError({"password": "Encrypted password required."})
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
        User is created or updated as inactive until email is verified.
        """
        email = validated_data["email"]
        password = validated_data["_decrypted_password"]

        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")
        organization = validated_data.get("organization", "")

        from authn.models import ContactEmail

        member = getattr(self, "_pending_member", None)
        if member is None:
            member = Member.objects.create_user(
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=False,
            )
            ContactEmail.objects.create(
                member=member,
                email_address=email,
                email_type="primary",
                verified=False,
            )
        else:
            member.first_name = first_name
            member.last_name = last_name
            member.is_active = False
            member.set_password(password)

        member.organization = organization or ""
        update_fields = ["first_name", "last_name", "organization", "is_active", "password", "updated_at"]
        member.save(update_fields=update_fields)

        issue_email_challenge(
            member=member,
            purpose=EmailAuthChallenge.Purpose.REGISTER,
            target_email=email,
        )

        return member
