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
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user's profile."""
        serializer = ProfileSerializer(instance=request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
