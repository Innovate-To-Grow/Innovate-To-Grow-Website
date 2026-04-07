"""
Authn app services.
"""

from .account import delete_member_account
from .contacts.contact_emails import (
    create_contact_email,
    delete_contact_email,
    make_contact_email_primary,
    resend_contact_email_verification,
    verify_contact_email_code,
)
from .contacts.contact_phones import (
    create_contact_phone,
    delete_contact_phone,
    request_phone_verification,
    verify_phone_code,
)
from .create_member import CreateMemberService
from .email.auth_email import (
    ResolvedAuthEmail,
    get_member_auth_emails,
    normalize_email,
    registration_email_conflicts,
    resolve_auth_email,
)
from .email_challenges import (
    AuthChallengeDeliveryError,
    AuthChallengeError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    consume_login_or_registration_challenge,
    consume_verification_token,
    issue_email_challenge,
    mark_challenge_verified,
    verify_email_code,
    verify_email_code_for_purposes,
)
from .import_members import (
    ImportResult,
    generate_template_excel,
    import_members_from_excel,
)
from .rsa_manager import (
    RSADecryptionError,
    decrypt_password,
    get_or_create_auth_keypair,
    get_public_key_pem,
    is_encrypted_password,
    rotate_auth_keypair,
)
from .sms import (
    PhoneVerificationDeliveryError,
    PhoneVerificationError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)

__all__ = [
    "CreateMemberService",
    "import_members_from_excel",
    "generate_template_excel",
    "ImportResult",
    "delete_member_account",
    # Auth email helpers
    "ResolvedAuthEmail",
    "normalize_email",
    "resolve_auth_email",
    "get_member_auth_emails",
    "registration_email_conflicts",
    "issue_email_challenge",
    "verify_email_code",
    "verify_email_code_for_purposes",
    "mark_challenge_verified",
    "consume_verification_token",
    "consume_login_or_registration_challenge",
    "AuthChallengeError",
    "AuthChallengeInvalid",
    "AuthChallengeThrottled",
    "AuthChallengeDeliveryError",
    # Contact emails
    "create_contact_email",
    "verify_contact_email_code",
    "resend_contact_email_verification",
    "delete_contact_email",
    "make_contact_email_primary",
    # Contact phones
    "create_contact_phone",
    "delete_contact_phone",
    "request_phone_verification",
    "verify_phone_code",
    # SMS exceptions
    "PhoneVerificationError",
    "PhoneVerificationInvalid",
    "PhoneVerificationThrottled",
    "PhoneVerificationDeliveryError",
    # RSA Manager
    "get_or_create_auth_keypair",
    "rotate_auth_keypair",
    "get_public_key_pem",
    "decrypt_password",
    "is_encrypted_password",
    "RSADecryptionError",
]
