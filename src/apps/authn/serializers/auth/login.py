"""
Login serializer for user authentication.
"""

from rest_framework import serializers

from apps.authn.services import login_guard, resolve_login_identifier

from ..helpers import decrypt_field

INVALID_CREDENTIALS = "Invalid credentials."


class LoginSerializer(serializers.Serializer):
    """
    Serializer for password login with an email **or** phone identifier.

    The password should be RSA encrypted with the public key. The legacy ``email``
    field is preserved for backward compatibility (clients post the identifier in
    it); ``identifier`` is an explicit alias and takes precedence when both are sent.

    Password guessing is bounded by ``login_guard``, keyed on the identifier: ``validate`` raises
    ``login_guard.LoginLocked`` (the view answers 429) before any decrypt or password hashing, counts each
    credential rejection, and clears the count on success. Malformed input never reaches the counters.
    """

    email = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Email address or phone number.",
    )
    identifier = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Email address or phone number (alias for email).",
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="RSA encrypted password (base64 encoded).",
    )
    key_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Key ID used for encryption (for key rotation handling).",
    )

    # noinspection PyMethodMayBeStatic
    def validate(self, attrs: dict) -> dict:
        identifier = (attrs.get("identifier") or attrs.get("email") or "").strip()
        key_id = attrs.get("key_id", "")

        # First, before the RSA decrypt and the PBKDF2 check: a locked identifier must cost nothing.
        login_guard.ensure_not_locked(identifier)

        try:
            password = decrypt_field(attrs.get("password", ""), key_id)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail}) from exc

        # Resolve the identifier to a member (verified email or verified phone), then
        # authenticate that member directly. Every failure mode returns the same
        # neutral error to avoid account enumeration, and counts the same against the lockout.
        resolved = resolve_login_identifier(identifier, require_active=False)
        if resolved is None or not resolved.member.is_active:
            login_guard.record_failure(identifier)
            raise serializers.ValidationError({"non_field_errors": [INVALID_CREDENTIALS]})

        member = resolved.member
        if not member.check_password(password):
            login_guard.record_failure(identifier)
            raise serializers.ValidationError({"non_field_errors": [INVALID_CREDENTIALS]})

        login_guard.clear(identifier)
        attrs["user"] = member
        return attrs
