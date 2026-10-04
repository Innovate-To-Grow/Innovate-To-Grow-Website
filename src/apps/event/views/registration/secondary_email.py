"""Event-scoped secondary email verification without account mutations."""

import logging

from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.models import EmailAuthChallenge
from apps.authn.services.email.auth_email import normalize_email
from apps.authn.services.email.challenges import (
    AuthChallengeInvalid,
    issue_email_challenge,
    verify_email_code_and_mint_token,
)
from apps.authn.services.send_verification import (
    OP_EVENT_SEND_SECONDARY_EMAIL_CODE,
    fingerprint_payload,
    guarded_send,
)
from apps.authn.services.send_verification.constants import EMAIL_CHANNEL, KIND_EMAIL
from apps.event.models import Event
from apps.event.throttles import EmailCodeUserRequestThrottle, SecondaryEmailCodeVerifyThrottle

logger = logging.getLogger(__name__)


class SecondaryEmailInputSerializer(serializers.Serializer):
    event_slug = serializers.SlugField()
    email = serializers.EmailField(max_length=254)


class SecondaryEmailCodeSerializer(SecondaryEmailInputSerializer):
    challenge_id = serializers.UUIDField()
    code = serializers.RegexField(r"^\d{6}$")


def _verification_input(request, serializer_class):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    event = Event.objects.filter(
        slug=data["event_slug"],
        registration_open=True,
        allow_secondary_email=True,
        verify_secondary_email=True,
    ).first()
    if event is None:
        raise ValidationError({"detail": "An open event requiring secondary email verification is required."})
    email = normalize_email(data["email"])
    if email == normalize_email(request.user.get_primary_email() or ""):
        raise ValidationError({"email": "Secondary email must be different from your primary email."})
    return data, email, f"event-registration:{event.pk}"


class SendSecondaryEmailCodeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeUserRequestThrottle]

    def post(self, request):
        _, email, context_identifier = _verification_input(request, SecondaryEmailInputSerializer)

        def perform():
            challenge = issue_email_challenge(
                member=request.user,
                purpose=EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
                target_email=email,
                context_identifier=context_identifier,
            )
            return {
                "detail": "Verification code sent.",
                "email": email,
                "challenge_id": str(challenge.pk),
            }, status.HTTP_200_OK

        return guarded_send(
            request,
            operation=OP_EVENT_SEND_SECONDARY_EMAIL_CODE,
            destination_kind=KIND_EMAIL,
            destination_normalized=email,
            fingerprint=fingerprint_payload({"email": email, "event": context_identifier}),
            channel=EMAIL_CHANNEL,
            perform=perform,
        )


class VerifySecondaryEmailCodeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SecondaryEmailCodeVerifyThrottle]

    def post(self, request):
        data, email, context_identifier = _verification_input(request, SecondaryEmailCodeSerializer)
        try:
            challenge, verification_token = verify_email_code_and_mint_token(
                purpose=EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
                target_email=email,
                code=data["code"],
                member=request.user,
                challenge_id=data["challenge_id"],
                context_identifier=context_identifier,
            )
        except AuthChallengeInvalid:
            return Response(
                {"detail": "Invalid or expired verification code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.warning("Secondary email verification failed", exc_info=True)
            return Response(
                {"detail": "Verification service is unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "detail": "Secondary email verified.",
                "email": email,
                "verified": True,
                "challenge_id": str(challenge.pk),
                "verification_token": verification_token,
            }
        )
