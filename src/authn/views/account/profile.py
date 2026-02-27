"""
Profile view for user information management.
"""

import base64
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import ProfileSerializer

logger = logging.getLogger(__name__)


class ProfileView(APIView):
    """
    API endpoint for user profile.
    GET: Retrieve current user's profile.
    PATCH: Update profile (JSON: first_name, last_name, display_name, organization;
           multipart: profile_image file).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user's profile."""
        try:
            serializer = ProfileSerializer(instance=request.user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Profile serialization failed for user %s", request.user.pk)
            return Response(
                {"detail": "Failed to load profile."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request):
        """Update current user's profile."""
        user = request.user

        # Handle multipart form (profile image upload)
        if request.FILES.get("profile_image"):
            profile = user.get_profile()
            file = request.FILES["profile_image"]
            content = file.read()
            b64 = base64.b64encode(content).decode("utf-8")
            content_type = getattr(file, "content_type", "image/png") or "image/png"
            profile.profile_image = f"data:{content_type};base64,{b64}"
            profile.save(update_fields=["profile_image", "updated_at"])
            serializer = ProfileSerializer(instance=user)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Handle JSON body (text fields)
        serializer = ProfileSerializer(instance=user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
