"""
Views for contact email management (CRUD + verification).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.models import ContactEmail
from authn.serializers import (
    ContactEmailCreateSerializer,
    ContactEmailSerializer,
    ContactEmailUpdateSerializer,
    ContactEmailVerifyCodeSerializer,
)
from authn.services import (
    AuthChallengeInvalid,
    create_contact_email,
    delete_contact_email,
    resend_contact_email_verification,
    verify_contact_email_code,
)

from ..helpers import challenge_error_response


def _get_contact_email(request, pk):
    return ContactEmail.objects.filter(pk=pk, member=request.user).first()


class ContactEmailListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emails = ContactEmail.objects.filter(member=request.user)
        serializer = ContactEmailSerializer(emails, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ContactEmailCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            contact_email = create_contact_email(
                member=request.user,
                email_address=serializer.validated_data["email_address"],
                email_type=serializer.validated_data["email_type"],
                subscribe=serializer.validated_data["subscribe"],
            )
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(ContactEmailSerializer(contact_email).data, status=status.HTTP_201_CREATED)


class ContactEmailDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ContactEmailUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        update_fields = []
        for field in ("email_type", "subscribe"):
            if field in serializer.validated_data:
                setattr(contact_email, field, serializer.validated_data[field])
                update_fields.append(field)

        if update_fields:
            contact_email.save(update_fields=update_fields + ["updated_at"])

        return Response(ContactEmailSerializer(contact_email).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        delete_contact_email(member=request.user, contact_email_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactEmailRequestVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if contact_email.verified:
            return Response({"detail": "This email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = resend_contact_email_verification(member=request.user, contact_email_id=pk)
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(result, status=status.HTTP_202_ACCEPTED)


class ContactEmailVerifyCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ContactEmailVerifyCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated = verify_contact_email_code(
                member=request.user,
                contact_email_id=pk,
                code=serializer.validated_data["code"],
            )
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(ContactEmailSerializer(updated).data, status=status.HTTP_200_OK)
