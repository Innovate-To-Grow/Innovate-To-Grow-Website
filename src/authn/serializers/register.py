"""
Registration serializer for user signup.
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

from authn.models.security import EmailAuthChallenge
from authn.serializers.helpers import decrypt_password_pair
from authn.services import issue_email_challenge, normalize_email, registration_email_conflicts

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
        required=True,
        max_length=150,
        help_text="User's first name.",
    )
    last_name = serializers.CharField(
        required=True,
        max_length=150,
        help_text="User's last name.",
    )
    organization = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Organization or company the user belongs to.",
    )
    title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Job title or position.",
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
        from authn.models import ContactEmail

        email_lower = normalize_email(value)
        pending_contact = (
            ContactEmail.objects.filter(email_address__iexact=email_lower, member__is_active=False)
            .select_related("member")
            .first()
        )
        pending_member = pending_contact.member if pending_contact else None
        if registration_email_conflicts(email_lower, exclude_member_id=pending_member.pk if pending_member else None):
            raise serializers.ValidationError("Unable to register with this email address.")
        self._pending_member = pending_member
        return email_lower

    # noinspection PyMethodMayBeStatic
    def validate(self, attrs: dict) -> dict:
        attrs["_decrypted_password"] = decrypt_password_pair(
            attrs,
            password_key="password",
            confirm_key="password_confirm",
        )
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
        title = validated_data.get("title", "")

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
        member.title = title or ""
        update_fields = ["first_name", "last_name", "organization", "title", "is_active", "password", "updated_at"]
        member.save(update_fields=update_fields)

        issue_email_challenge(
            member=member,
            purpose=EmailAuthChallenge.Purpose.REGISTER,
            target_email=email,
        )

        return member
