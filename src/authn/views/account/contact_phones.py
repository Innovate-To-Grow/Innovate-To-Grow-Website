"""
Views for contact phone management (list, create, update, delete).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.models import ContactPhone
from authn.serializers import (
    ContactPhoneCreateSerializer,
    ContactPhoneSerializer,
    ContactPhoneUpdateSerializer,
    ContactPhoneVerifyCodeSerializer,
)
from authn.services import (
    create_contact_phone,
    delete_contact_phone,
    request_phone_verification,
    verify_phone_code,
    PhoneVerificationDeliveryError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)
from authn.services.email_challenges import AuthChallengeInvalid


class ContactPhoneListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        phones = ContactPhone.objects.filter(member=request.user)
        serializer = ContactPhoneSerializer(phones, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = ContactPhoneCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            contact_phone = create_contact_phone(
                member=request.user,
                phone_number=serializer.validated_data["phone_number"],
                region=serializer.validated_data["region"],
                subscribe=serializer.validated_data["subscribe"],
            )
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ContactPhoneSerializer(contact_phone).data, status=status.HTTP_201_CREATED)


class ContactPhoneDetailView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def patch(self, request, pk):
        contact_phone = ContactPhone.objects.filter(pk=pk, member=request.user).first()
        if contact_phone is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ContactPhoneUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        contact_phone.subscribe = serializer.validated_data["subscribe"]
        contact_phone.save(update_fields=["subscribe", "updated_at"])

        return Response(ContactPhoneSerializer(contact_phone).data, status=status.HTTP_200_OK)

    # noinspection PyMethodMayBeStatic
    def delete(self, request, pk):
        try:
            delete_contact_phone(member=request.user, contact_phone_id=pk)
        except AuthChallengeInvalid:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactPhoneRequestVerificationView(APIView):
    """Request an SMS verification code for a contact phone."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        try:
            result = request_phone_verification(member=request.user, contact_phone_id=pk)
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PhoneVerificationThrottled as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except PhoneVerificationDeliveryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(result, status=status.HTTP_202_ACCEPTED)


class ContactPhoneVerifyCodeView(APIView):
    """Verify an SMS code for a contact phone."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        serializer = ContactPhoneVerifyCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated = verify_phone_code(
                member=request.user,
                contact_phone_id=pk,
                code=serializer.validated_data["code"],
            )
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PhoneVerificationInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PhoneVerificationThrottled as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        return Response(ContactPhoneSerializer(updated).data, status=status.HTTP_200_OK)
