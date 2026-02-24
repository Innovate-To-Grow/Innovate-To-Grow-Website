"""
Profile serializer for user information.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

Member = get_user_model()


class ProfileSerializer(serializers.Serializer):
    """
    Serializer for user profile information.
    """

    member_uuid = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance: Member) -> dict:
        """
        Get profile data from the user instance.
        """
        return {
            "member_uuid": str(instance.member_uuid),
            "email": instance.email,
            "username": instance.username,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "display_name": instance.get_full_name() or instance.username,
            "is_active": instance.is_active,
            "date_joined": instance.date_joined.isoformat(),
        }
