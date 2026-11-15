"""Serializers for email-code auth flows."""

from .account import AccountEmailsSerializer
from .account_deletion import (
    DeleteAccountCodeConfirmSerializer,
    DeleteAccountCodeRequestSerializer,
    DeleteAccountCodeVerifySerializer,
)
from .auth import (
    LoginCodeRequestSerializer,
    LoginCodeVerifySerializer,
    RegisterResendCodeSerializer,
    RegisterVerifyCodeSerializer,
    UnifiedEmailAuthRequestSerializer,
    UnifiedEmailAuthVerifySerializer,
)
from .password_change import (
    ChangePasswordCodeConfirmSerializer,
    ChangePasswordCodeRequestSerializer,
    ChangePasswordCodeVerifySerializer,
)
from .password_reset_confirm import PasswordResetConfirmSerializer, PasswordResetVerifySerializer
from .password_reset_request import PasswordResetRequestSerializer

__all__ = [
    "AccountEmailsSerializer",
    "ChangePasswordCodeConfirmSerializer",
    "ChangePasswordCodeRequestSerializer",
    "ChangePasswordCodeVerifySerializer",
    "DeleteAccountCodeConfirmSerializer",
    "DeleteAccountCodeRequestSerializer",
    "DeleteAccountCodeVerifySerializer",
    "LoginCodeRequestSerializer",
    "LoginCodeVerifySerializer",
    "PasswordResetConfirmSerializer",
    "PasswordResetRequestSerializer",
    "PasswordResetVerifySerializer",
    "RegisterResendCodeSerializer",
    "RegisterVerifyCodeSerializer",
    "UnifiedEmailAuthRequestSerializer",
    "UnifiedEmailAuthVerifySerializer",
]
