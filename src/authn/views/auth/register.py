"""
Registration view for user signup.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from authn.serializers import RegisterSerializer
from authn.throttles import LoginRateThrottle


class RegisterView(APIView):
    """
    API endpoint for user registration.
    Creates an active user and returns JWT tokens immediately.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        member = serializer.save()

        refresh = RefreshToken.for_user(member)

        return Response(
            {
                "message": "Registration successful.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "member_uuid": str(member.id),
                    "email": member.email,
                    "username": member.username,
                    "display_name": member.get_full_name() or member.username,
                },
            },
            status=status.HTTP_201_CREATED,
        )
