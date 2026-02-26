"""
Change password view for authenticated users.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import ChangePasswordSerializer


class ChangePasswordView(APIView):
    """
    API endpoint for changing the authenticated user's password.
    POST: Change password with current password verification.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Change the user's password."""
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Set new password
        new_password = serializer.validated_data["_decrypted_new_password"]
        request.user.set_password(new_password)
        request.user.save()

        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )
