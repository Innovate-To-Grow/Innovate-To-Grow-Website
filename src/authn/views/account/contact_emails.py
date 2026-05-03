"""
Views for contact email management (CRUD + verification).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.models import ContactEmail
from authn.security_messages import (
    CONTACT_EMAIL_ADD_FAILED,
    CONTACT_EMAIL_PRIMARY_FAILED,
    CONTACT_EMAIL_SEND_FAILED,
    VERIFICATION_INVALID,
)
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
    make_contact_email_primary,
    resend_contact_email_verification,
    verify_contact_email_code,
)
from authn.throttles import ContactEmailCreateThrottle, EmailCodeRequestThrottle, EmailCodeVerifyThrottle

from ..helpers import challenge_error_response


def _get_contact_email(request, pk):
    return ContactEmail.objects.filter(pk=pk, member=request.user).first()


class ContactEmailListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == "POST":
            return [ContactEmailCreateThrottle()]
        return []

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        emails = ContactEmail.objects.filter(member=request.user).exclude(email_type="primary")
        serializer = ContactEmailSerializer(emails, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # noinspection PyMethodMayBeStatic
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
        except AuthChallengeInvalid:
            return Response({"detail": CONTACT_EMAIL_ADD_FAILED}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(ContactEmailSerializer(contact_email).data, status=status.HTTP_201_CREATED)


class ContactEmailDetailView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def patch(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ContactEmailUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if serializer.validated_data.get("email_type") == "secondary":
            if ContactEmail.objects.filter(member=request.user, email_type="secondary").exclude(pk=pk).exists():
                return Response(
                    {"email_type": ["You already have a secondary email."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        update_fields = []
        for field in ("email_type", "subscribe"):
            if field in serializer.validated_data:
                setattr(contact_email, field, serializer.validated_data[field])
                update_fields.append(field)

        if update_fields:
            contact_email.save(update_fields=update_fields + ["updated_at"])

        return Response(ContactEmailSerializer(contact_email).data, status=status.HTTP_200_OK)

    # noinspection PyMethodMayBeStatic
    def delete(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        delete_contact_email(member=request.user, contact_email_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactEmailRequestVerificationView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if contact_email.verified:
            return Response({"detail": "This email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = resend_contact_email_verification(member=request.user, contact_email_id=pk)
        except AuthChallengeInvalid:
            return Response({"detail": CONTACT_EMAIL_SEND_FAILED}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(result, status=status.HTTP_202_ACCEPTED)


class ContactEmailVerifyCodeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
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
        except AuthChallengeInvalid:
            return Response({"detail": VERIFICATION_INVALID}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(ContactEmailSerializer(updated).data, status=status.HTTP_200_OK)


class ContactEmailMakePrimaryView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            updated = make_contact_email_primary(member=request.user, contact_email_id=pk)
        except AuthChallengeInvalid:
            return Response({"detail": CONTACT_EMAIL_PRIMARY_FAILED}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)

        return Response(ContactEmailSerializer(updated).data, status=status.HTTP_200_OK)
