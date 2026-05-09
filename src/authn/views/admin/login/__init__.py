from django.contrib.auth import get_user_model

from authn.forms.admin_login import (
    AdminCodeForm,
    AdminEmailForm,
    AdminPasswordForm,
    AdminRememberedPasswordForm,
)
from authn.models.security import EmailAuthChallenge
from authn.services.email_challenges import (
    AuthChallengeDeliveryError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    consume_login_or_registration_challenge,
    issue_email_challenge,
    verify_email_code,
)

from .view import AdminLoginView

Member = get_user_model()
PURPOSE = EmailAuthChallenge.Purpose.ADMIN_LOGIN

__all__ = [
    "AdminCodeForm",
    "AdminEmailForm",
    "AdminLoginView",
    "AdminPasswordForm",
    "AdminRememberedPasswordForm",
    "AuthChallengeDeliveryError",
    "AuthChallengeInvalid",
    "AuthChallengeThrottled",
    "Member",
    "PURPOSE",
    "consume_login_or_registration_challenge",
    "issue_email_challenge",
    "verify_email_code",
]
