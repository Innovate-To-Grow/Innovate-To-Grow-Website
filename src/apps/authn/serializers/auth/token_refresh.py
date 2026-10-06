"""
Refresh-token serializer that treats a deleted member as an invalid token.
"""

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer


class MemberTokenRefreshSerializer(TokenRefreshSerializer):
    """SimpleJWT looks the token's member up with ``objects.get`` and lets ``DoesNotExist`` escape, so a
    refresh token whose member was hard-deleted answers HTTP 500. Report it as an invalid token (401)
    instead, which clients treat as a dead session rather than a transient failure.
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist as exc:
            raise InvalidToken() from exc
