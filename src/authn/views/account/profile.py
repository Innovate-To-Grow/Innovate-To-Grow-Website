"""
Profile view for user information management.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import ProfileSerializer


class ProfileView(APIView):
    """
    API endpoint for user profile.
    GET: Retrieve current user's profile.
    PATCH: Update current user's profile (display_name).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user's profile."""
        serializer = ProfileSerializer(instance=request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        """Update current user's profile."""
        serializer = ProfileSerializer(instance=request.user, data=request.data, partial=True)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.update(request.user, serializer.validated_data)

        # Return updated profile
        return Response(
            ProfileSerializer(instance=request.user).data,
            status=status.HTTP_200_OK,
        )
