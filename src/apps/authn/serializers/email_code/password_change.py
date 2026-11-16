"""Password create/change for a signed-in member: request a code, check it, set the new password (account deletion:
``account_deletion.py``)."""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.authn.constants import RECOVERY_CHANNEL_UNAVAILABLE, VERIFICATION_INVALID
from apps.authn.services import (
    AuthChallengeInvalid,
    NoRecoveryChannelError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    consume_verification_token,
    get_member_auth_emails,
    issue_email_challenge,
    normalize_email,
    request_sms_password_code,
    select_recovery_channel,
    verify_email_code_and_mint_token,
    verify_sms_password_code_and_mint,
)

from ..shared.encrypted_passwords import decrypt_password_pair
from .base import PURPOSE


class ChangePasswordCodeRequestSerializer(serializers.Serializer):
    """Request a password-create/change verification code.

    The verification channel is chosen by ``select_recovery_channel`` (verified
    primary email -> any verified email -> verified phone via SMS). ``email`` is
    optional and only used to disambiguate when the member has several verified
    emails (legacy clients echo it); it must be one of the member's verified emails.
    """

    email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        member = self.context["request"].user
        requested = normalize_email(attrs["email"]) if attrs.get("email") else None
        if requested and requested not in set(get_member_auth_emails(member)):
            raise serializers.ValidationError({"email": "This email is not eligible for password change verification."})
        try:
            attrs["selected"] = select_recovery_channel(member, requested_email=requested)
        except NoRecoveryChannelError:
            raise serializers.ValidationError({"detail": RECOVERY_CHANNEL_UNAVAILABLE}) from None
        return attrs

    def save(self):
        member = self.context["request"].user
        selected = self.validated_data["selected"]
        if selected.channel == "email":
            issue_email_challenge(
                member=member,
                purpose=PURPOSE.PASSWORD_CHANGE,
                target_email=selected.target_email,
            )
        else:
            challenge_id = request_sms_password_code(
                member=member,
                e164=selected.e164,
                purpose=PURPOSE.PASSWORD_CHANGE,
            )
        payload = {
            "message": "Verification code sent.",
            "channel": selected.channel,
            "destination": selected.masked_destination,
        }
        if selected.channel == "sms":
            payload["challenge_id"] = challenge_id
        return payload


class ChangePasswordCodeVerifySerializer(serializers.Serializer):
    """Verify a password-change code (email or SMS) and mint a verification token.

    The channel is re-derived deterministically from member state, so the same
    channel chosen at request time is used here; ``email`` disambiguates the email
    case for members with several verified emails.
    """

    email = serializers.EmailField(required=False, allow_blank=True)
    code = serializers.CharField(required=True, min_length=6, max_length=6)
    channel = serializers.ChoiceField(choices=["email", "sms"], required=False)
    challenge_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict) -> dict:
        member = self.context["request"].user
        requested = normalize_email(attrs["email"]) if attrs.get("email") else None
        try:
            selected = select_recovery_channel(member, requested_email=requested)
        except NoRecoveryChannelError:
            raise serializers.ValidationError({"detail": RECOVERY_CHANNEL_UNAVAILABLE}) from None

        client_channel = attrs.get("channel")
        if client_channel and client_channel != selected.channel:
            raise serializers.ValidationError(
                {"detail": "Your contact methods changed since the code was sent. Please request a new code."}
            )

        if selected.channel == "email":
            try:
                _, attrs["verification_token"] = verify_email_code_and_mint_token(
                    purpose=PURPOSE.PASSWORD_CHANGE,
                    target_email=selected.target_email,
                    code=attrs["code"],
                    member=member,
                )
            except AuthChallengeInvalid:
                raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from None
        else:
            try:
                attrs["verification_token"] = verify_sms_password_code_and_mint(
                    member=member,
                    purpose=PURPOSE.PASSWORD_CHANGE,
                    e164=selected.e164,
                    code=attrs["code"],
                    challenge_id=attrs.get("challenge_id"),
                )
            except (PhoneVerificationInvalid, PhoneVerificationThrottled):
                raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from None

        attrs["channel"] = selected.channel
        return attrs

    def save(self):
        return {
            "message": "Verification code accepted.",
            "verification_token": self.validated_data["verification_token"],
            "channel": self.validated_data["channel"],
        }


class ChangePasswordCodeConfirmSerializer(serializers.Serializer):
    verification_token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)
    key_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        attrs["decrypted_new_password"] = decrypt_password_pair(attrs, user=self.context["request"].user)
        return attrs

    def save(self):
        member = self.context["request"].user
        new_password = self.validated_data["decrypted_new_password"]
        validate_password(new_password, user=member)
        consume_verification_token(
            purpose=PURPOSE.PASSWORD_CHANGE,
            verification_token=self.validated_data["verification_token"],
            member=member,
        )
        member.set_password(new_password)
        member.save(update_fields=["password"])
        return {"message": "Password changed successfully."}
