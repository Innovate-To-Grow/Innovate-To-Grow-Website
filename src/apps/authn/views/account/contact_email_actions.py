"""Actions on one contact email: send it a verification code, check the code, make it the primary address."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.constants import (
    CONTACT_EMAIL_PRIMARY_FAILED,
    VERIFICATION_INVALID,
)
from apps.authn.security.throttles import (
    EmailCodeUserRequestThrottle,
    EmailCodeVerifyThrottle,
)
from apps.authn.serializers import (
    ContactEmailSerializer,
    ContactEmailVerifyCodeSerializer,
)
from apps.authn.services import (
    AuthChallengeInvalid,
    make_contact_email_primary,
    resend_contact_email_verification,
    verify_contact_email_code,
)
from apps.authn.services.email.auth_email import normalize_email
from apps.authn.services.send_verification import (
    OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
    fingerprint_payload,
    guarded_send,
)
from apps.authn.services.send_verification.rules.constants import EMAIL_CHANNEL, KIND_EMAIL

from ..shared.responses import challenge_error_response
from .contact_emails import _get_contact_email


class ContactEmailRequestVerificationView(APIView):
    rate_limit_scope = "auth-code-send"
    permission_classes = [IsAuthenticated]
    # Per-user cap: an anonymous (per-IP) throttle never fires for an
    # authenticated caller, leaving SES sends to an attacker-supplied address
    # unbounded.
    throttle_classes = [EmailCodeUserRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        contact_email = _get_contact_email(request, pk)
        if contact_email is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if contact_email.verified:
            return Response({"detail": "This email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        def perform():
            result = resend_contact_email_verification(member=request.user, contact_email_id=pk)
            return result, status.HTTP_202_ACCEPTED

        return guarded_send(
            request,
            operation=OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
            destination_kind=KIND_EMAIL,
            destination_normalized=normalize_email(contact_email.email_address),
            fingerprint=fingerprint_payload({"contact_id": str(pk)}),
            channel=EMAIL_CHANNEL,
            perform=perform,
        )


class ContactEmailVerifyCodeView(APIView):
    rate_limit_scope = "auth-code-verify"
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
    rate_limit_scope = "member-write"
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
