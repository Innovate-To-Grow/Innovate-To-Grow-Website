"""
Authn app services.
"""

from .auth_email import (
    ResolvedAuthEmail,
    get_member_auth_emails,
    normalize_email,
    registration_email_conflicts,
    resolve_auth_email,
)
from .auth_mail import AuthEmailError, send_auth_code_email
from .create_member import CreateMemberService
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

__all__ = [
    "CreateMemberService",
    "import_members_from_excel",
    "generate_template_excel",
    "ImportResult",
    # Auth email helpers
    "ResolvedAuthEmail",
    "normalize_email",
    "resolve_auth_email",
    "get_member_auth_emails",
    "registration_email_conflicts",
    "send_auth_code_email",
    "AuthEmailError",
    "issue_email_challenge",
    "verify_email_code",
    "mark_challenge_verified",
    "consume_verification_token",
    "consume_login_or_registration_challenge",
    "AuthChallengeError",
    "AuthChallengeInvalid",
    "AuthChallengeThrottled",
    "AuthChallengeDeliveryError",
    # RSA Manager
    "get_or_create_auth_keypair",
    "rotate_auth_keypair",
    "get_public_key_pem",
    "decrypt_password",
    "is_encrypted_password",
    "RSADecryptionError",
]
