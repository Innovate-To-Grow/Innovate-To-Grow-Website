"""Account-deletion code serializers: request, verify, and confirm (which deletes the account)."""

from __future__ import annotations

from rest_framework import serializers

from apps.authn.constants import VERIFICATION_INVALID
from apps.authn.services import (
    AuthChallengeInvalid,
    consume_verification_token,
    delete_member_account,
    issue_email_challenge,
    normalize_email,
    verify_email_code_and_mint_token,
)

from .base import PURPOSE, BaseCodeVerifySerializer


class DeleteAccountCodeRequestSerializer(serializers.Serializer):
    def validate(self, attrs):
        member = self.context["request"].user
        email = member.get_primary_email()
        if not email:
            raise serializers.ValidationError(
                {"detail": "No verified email is available for account deletion. Add and verify an email first."}
            )
        attrs["target_email"] = normalize_email(email)
        return attrs

    def save(self):
        member = self.context["request"].user
        issue_email_challenge(
            member=member,
            purpose=PURPOSE.ACCOUNT_DELETE,
            target_email=self.validated_data["target_email"],
        )
        return {"message": "Deletion verification code sent."}


class DeleteAccountCodeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_code(self, value: str) -> str:
        return BaseCodeVerifySerializer().validate_code(value)

    def validate(self, attrs: dict) -> dict:
        member = self.context["request"].user
        email = member.get_primary_email()
        if not email:
            raise serializers.ValidationError(
                {"detail": "No verified email is available for account deletion. Add and verify an email first."}
            )

        try:
            challenge, verification_token = verify_email_code_and_mint_token(
                purpose=PURPOSE.ACCOUNT_DELETE,
                target_email=email,
                code=attrs["code"],
                member=member,
            )
        except AuthChallengeInvalid:
            raise serializers.ValidationError({"detail": VERIFICATION_INVALID}) from None

        if challenge.member != member:
            raise serializers.ValidationError({"detail": VERIFICATION_INVALID})

        attrs["challenge"] = challenge
        attrs["verification_token"] = verification_token
        return attrs

    def save(self):
        return {
            "message": "Deletion verification code accepted.",
            "verification_token": self.validated_data["verification_token"],
        }


class DeleteAccountCodeConfirmSerializer(serializers.Serializer):
    verification_token = serializers.CharField(required=True)

    def save(self):
        member = self.context["request"].user
        consume_verification_token(
            purpose=PURPOSE.ACCOUNT_DELETE,
            verification_token=self.validated_data["verification_token"],
            member=member,
        )
        delete_member_account(member=member)
        return {"message": "Account deleted successfully."}
