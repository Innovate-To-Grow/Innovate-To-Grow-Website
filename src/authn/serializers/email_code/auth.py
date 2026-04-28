"""Login, registration, and unified email auth serializers."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from authn.security_messages import VERIFICATION_INVALID
from authn.services import (
    AuthChallengeInvalid,
    issue_email_challenge,
    registration_email_conflicts,
    resolve_auth_email,
    verify_email_code_for_purposes,
)

from .base import _CODE_RE, PURPOSE, BaseCodeVerifySerializer, BaseEmailSerializer

Member = get_user_model()
EMAIL_AUTH_SOURCE_CHOICES = (
    ("login", "login"),
    ("subscribe", "subscribe"),
    ("event_registration", "event_registration"),
)


class LoginCodeRequestSerializer(BaseEmailSerializer):
    def save(self):
        resolved = resolve_auth_email(self.validated_data["email"], require_active=True)
        if resolved is not None:
            issue_email_challenge(
                member=resolved.member,
                purpose=PURPOSE.LOGIN,
                target_email=resolved.delivery_email,
                link_flow="login",
                link_source="login",
            )
        return {"message": "If an eligible account exists, a verification code has been sent."}


class LoginCodeVerifySerializer(BaseCodeVerifySerializer):
    purpose = PURPOSE.LOGIN


class UnifiedEmailAuthRequestSerializer(BaseEmailSerializer):
    source = serializers.ChoiceField(choices=EMAIL_AUTH_SOURCE_CHOICES, required=False, default="login")

    def _create_pending_member(self, email: str) -> Member:
        from authn.models import ContactEmail

        member = Member(
            is_active=False,
            first_name="",
            last_name="",
            organization="",
        )
        member.set_unusable_password()
        member.save()
        ContactEmail.objects.create(
            member=member,
            email_address=email,
            email_type="primary",
            verified=False,
            subscribe=True,
        )
        return member

    def save(self):
        email = self.validated_data["email"]
        source = self.validated_data["source"]
        generic_response = {"message": "Check your email for a verification code."}
        resolved = resolve_auth_email(email, require_active=True)
        if resolved is not None:
            issue_email_challenge(
                member=resolved.member,
                purpose=PURPOSE.LOGIN,
                target_email=resolved.delivery_email,
                link_flow="auth",
                link_source=source,
            )
            return generic_response

        from authn.models import ContactEmail

        pending_contact = (
            ContactEmail.objects.filter(email_address__iexact=email, member__is_active=False)
            .select_related("member")
            .first()
        )
        pending_member = pending_contact.member if pending_contact else None
        if registration_email_conflicts(email, exclude_member_id=pending_member.pk if pending_member else None):
            raise serializers.ValidationError({"email": "This email cannot be used for registration."})

        member = pending_member or self._create_pending_member(email)
        issue_email_challenge(
            member=member,
            purpose=PURPOSE.REGISTER,
            target_email=email,
            link_flow="auth",
            link_source=source,
        )
        return generic_response


class UnifiedEmailAuthVerifySerializer(BaseEmailSerializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_code(self, value: str) -> str:
        normalized = value.strip()
        if not _CODE_RE.match(normalized):
            raise serializers.ValidationError("Code must be a 6-digit number.")
        return normalized

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        try:
            challenge = verify_email_code_for_purposes(
                purposes=[PURPOSE.LOGIN, PURPOSE.REGISTER],
                target_email=attrs["email"],
                code=attrs["code"],
            )
        except AuthChallengeInvalid as exc:
            raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from exc

        attrs["challenge"] = challenge
        attrs["flow"] = "register" if challenge.purpose == PURPOSE.REGISTER else "login"
        return attrs


class RegisterVerifyCodeSerializer(BaseCodeVerifySerializer):
    purpose = PURPOSE.REGISTER


class RegisterResendCodeSerializer(BaseEmailSerializer):
    def save(self):
        from authn.models import ContactEmail

        contact = (
            ContactEmail.objects.filter(email_address__iexact=self.validated_data["email"], member__is_active=False)
            .select_related("member")
            .first()
        )
        member = contact.member if contact else None
        if member is None:
            raise serializers.ValidationError({"email": "No pending registration was found for this email."})
        issue_email_challenge(
            member=member,
            purpose=PURPOSE.REGISTER,
            target_email=self.validated_data["email"],
            link_flow="register",
            link_source="register",
        )
        return {"message": "Verification code sent."}
