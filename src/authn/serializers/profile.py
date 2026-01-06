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
    Supports reading user info and updating display_name.
    """

    member_uuid = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="User display name.",
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

        return instance

