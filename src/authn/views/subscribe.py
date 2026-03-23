"""
View for public email subscription.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import SubscribeSerializer
from authn.throttles import EmailCodeRequestThrottle


class SubscribeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = SubscribeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        _contact, created = serializer.save()
        return Response(
            {"message": "You have been subscribed successfully."},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
