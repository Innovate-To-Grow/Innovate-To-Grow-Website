"""
Profile serializer for user information.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from authn.models import MemberProfile

Member = get_user_model()


class ProfileSerializer(serializers.Serializer):
    """
    Serializer for user profile information.
    """

    member_uuid = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    username = serializers.CharField(read_only=True)
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
    display_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="User display name.",
    )
    organization = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Organization or company the user belongs to.",
    )
    is_active = serializers.BooleanField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance: Member) -> dict:
        """
        Get profile data from the user instance.
        """
        profile = instance.get_profile()
        return {
            "member_uuid": str(instance.member_uuid),
            "email": instance.email,
            "username": instance.username,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "display_name": profile.display_name or "",
            "organization": instance.organization or "",
            "is_active": instance.is_active,
            "date_joined": instance.date_joined.isoformat(),
        }

    def update(self, instance: Member, validated_data: dict) -> Member:
        """
        Update the user's profile with the validated data.
        """
        display_name = validated_data.get("display_name")
        if display_name is not None:
            profile, _ = MemberProfile.objects.get_or_create(model_user=instance)
            profile.display_name = display_name
            profile.save(update_fields=["display_name", "updated_at"])

        # Update Member model fields
        member_fields_to_update = []
        for field in ("first_name", "last_name", "organization"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
                member_fields_to_update.append(field)

        if member_fields_to_update:
            instance.save(update_fields=member_fields_to_update)

        return instance
