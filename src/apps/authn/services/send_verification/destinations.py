from __future__ import annotations

from uuid import UUID

from rest_framework.exceptions import PermissionDenied, ValidationError

from .constants import (
    AUTHENTICATED_OPERATIONS,
    KIND_EMAIL,
    KIND_PHONE,
    OP_ADMIN_LOGIN_REMEMBERED_CODE,
    OP_ADMIN_LOGIN_REQUEST_CODE,
    OP_ADMIN_LOGIN_RESEND,
    OP_CHANGE_PASSWORD_REQUEST_CODE,
    OP_CONTACT_EMAIL_CREATE,
    OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
    OP_CONTACT_PHONE_REQUEST_VERIFICATION,
    OP_DELETE_ACCOUNT_REQUEST_CODE,
    OP_EVENT_SEND_PHONE_CODE,
    OP_PASSWORD_RESET_REQUEST_CODE,
    SMS_OPERATIONS,
)
from .exceptions import SendVerificationInvalid


def _parse_uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def resolve_operation_destination(request, *, operation: str, data: dict) -> tuple[str, str]:
    """Resolve challenge input using the corresponding operation's business policy.

    The challenge API accepts destination as a convenience alias. Sending views
    must derive their context from validated business fields, not this alias.
    """
    user = getattr(request, "user", None)
    authenticated = bool(user is not None and getattr(user, "is_authenticated", False))
    if operation in AUTHENTICATED_OPERATIONS and not authenticated:
        raise PermissionDenied()
    if operation in {
        OP_ADMIN_LOGIN_REQUEST_CODE,
        OP_ADMIN_LOGIN_REMEMBERED_CODE,
        OP_ADMIN_LOGIN_RESEND,
    }:
        return KIND_EMAIL, _resolve_admin_login(request, operation, data)

    if operation in SMS_OPERATIONS or operation == OP_CONTACT_PHONE_REQUEST_VERIFICATION:
        return KIND_PHONE, _resolve_phone(request, operation, data)
    if operation == OP_PASSWORD_RESET_REQUEST_CODE:
        return _resolve_password_reset(data)
    if operation == OP_CHANGE_PASSWORD_REQUEST_CODE:
        return _resolve_change_password(request, data)
    if operation == OP_DELETE_ACCOUNT_REQUEST_CODE:
        email = user.get_primary_email()
        if not email:
            raise ValidationError({"detail": "No verified email is available for account deletion."})
        from apps.authn.services.email.auth_email import normalize_email

        return KIND_EMAIL, normalize_email(email)
    if operation == OP_CONTACT_EMAIL_REQUEST_VERIFICATION:
        return KIND_EMAIL, _resolve_contact_email(request, data)
    if operation == OP_CONTACT_EMAIL_CREATE:
        from apps.authn.services.email.auth_email import normalize_email

        return KIND_EMAIL, normalize_email(
            str(data.get("destination") or data.get("email_address") or data.get("email") or "")
        )
    email = str(data.get("destination") or data.get("email") or data.get("identifier") or "")
    from apps.authn.services.email.auth_email import normalize_email

    normalized = normalize_email(email)
    if not normalized:
        raise ValidationError({"destination": "A destination is required."})
    return KIND_EMAIL, normalized


def _resolve_phone(request, operation: str, data: dict) -> str:
    from apps.authn.services.contacts.contact_phones import national_to_e164, normalize_to_national

    if operation == OP_CONTACT_PHONE_REQUEST_VERIFICATION:
        contact_id = _parse_uuid(data.get("contact_id") or data.get("id"))
        if contact_id is None:
            raise ValidationError({"contact_id": "A contact id is required."})
        from apps.authn.models import ContactPhone

        contact = ContactPhone.objects.filter(pk=contact_id, member=request.user).first()
        if contact is None:
            raise SendVerificationInvalid("Contact phone not found.")
        return national_to_e164(contact.phone_number, contact.region)
    phone = str(data.get("destination") or data.get("phone") or data.get("phone_number") or "")
    region = "1-US" if operation == OP_EVENT_SEND_PHONE_CODE else str(data.get("region") or "1-US")
    if not phone:
        raise ValidationError({"destination": "A phone number is required."})
    national = normalize_to_national(phone, region)
    return national_to_e164(national, region)


def _resolve_password_reset(data: dict) -> tuple[str, str]:
    from apps.authn.serializers import PasswordResetRequestSerializer

    identifier = data.get("identifier") or data.get("email") or data.get("destination") or ""
    serializer = PasswordResetRequestSerializer(data={"identifier": identifier})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["destination_kind"], serializer.validated_data["destination_normalized"]


def _resolve_change_password(request, data: dict) -> tuple[str, str]:
    from apps.authn.serializers import ChangePasswordCodeRequestSerializer

    requested = data.get("email") or ""
    serializer = ChangePasswordCodeRequestSerializer(data={"email": requested}, context={"request": request})
    serializer.is_valid(raise_exception=True)
    selected = serializer.validated_data["selected"]
    if selected.channel == "sms":
        return KIND_PHONE, selected.e164
    return KIND_EMAIL, selected.target_email


def _resolve_admin_login(request, operation: str, data: dict) -> str:
    from apps.authn.services.email.auth_email import normalize_email
    from apps.authn.views.admin.login_helpers import get_admin_login_state, get_last_admin_login_member

    supplied = normalize_email(str(data.get("destination") or data.get("email") or ""))
    if operation == OP_ADMIN_LOGIN_REQUEST_CODE:
        if not supplied:
            raise ValidationError({"destination": "An email is required."})
        return supplied
    if operation == OP_ADMIN_LOGIN_REMEMBERED_CODE:
        member = get_last_admin_login_member(request)
        contact = member.get_primary_contact_email() if member else None
        if contact is None or not contact.verified:
            raise ValidationError({"detail": "Unable to send verification code."})
        return normalize_email(contact.email_address)
    _step, email, _member_id = get_admin_login_state(request)
    normalized = normalize_email(email or supplied)
    if not normalized:
        raise ValidationError({"destination": "An email is required."})
    return normalized


def _resolve_contact_email(request, data: dict) -> str:
    from apps.authn.models import ContactEmail
    from apps.authn.services.email.auth_email import normalize_email

    contact_id = _parse_uuid(data.get("contact_id") or data.get("id"))
    if contact_id is None:
        raise ValidationError({"contact_id": "A contact id is required."})
    contact = ContactEmail.objects.filter(pk=contact_id, member=request.user).first()
    if contact is None:
        raise SendVerificationInvalid("Contact email not found.")
    return normalize_email(contact.email_address)
