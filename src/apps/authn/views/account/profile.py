"""
Profile view for user information management.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.serializers import ProfileSerializer
from apps.authn.services.members.profile_image import ProfileImageError, detect_image_mime, encode_profile_image

logger = logging.getLogger(__name__)


def _validate_image_bytes(data: bytes) -> bool:
    """Validate that file content starts with a known image magic-byte signature.

    Kept as a thin alias over the shared helper; existing tests import it from here.
    """
    return detect_image_mime(data) is not None


class ProfileView(APIView):
    """
    API endpoint for user profile.
    GET: Retrieve current user's profile.
    PATCH: Update profile (JSON: first_name, last_name, organization;
           multipart: profile_image file).
    """

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        """Get current user's profile."""
        try:
            serializer = ProfileSerializer(instance=request.user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (ValueError, TypeError, AttributeError):
            logger.exception("Profile serialization failed for user %s", request.user.pk)
            return Response(
                {"detail": "Failed to load profile."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # noinspection PyMethodMayBeStatic
    def patch(self, request):
        """Update current user's profile."""
        user = request.user

        # Handle multipart form (profile image upload)
        if request.FILES.get("profile_image"):
            try:
                # Shared with the Django admin change form so both paths enforce the same size cap,
                # content-type allow-list and magic-byte check, and both downscale before storing.
                user.profile_image = encode_profile_image(request.FILES["profile_image"])
            except ProfileImageError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            user.save(update_fields=["profile_image", "updated_at"])
            serializer = ProfileSerializer(instance=user)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Handle JSON body (text fields)
        serializer = ProfileSerializer(instance=user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
