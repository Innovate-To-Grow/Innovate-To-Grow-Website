"""
Login view for user authentication.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from authn.serializers import LoginSerializer
from authn.throttles import LoginRateThrottle


class LoginView(APIView):
    """
    API endpoint for user login.
    Returns JWT access and refresh tokens.
    """

    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Login successful.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "member_uuid": str(user.member_uuid),
                    "email": user.email,
                    "username": user.username,
                    "display_name": user.get_full_name() or user.username,
                },
            },
            status=status.HTTP_200_OK,
        )
