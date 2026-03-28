"""Serializers for email-code auth flows."""

from .account import AccountEmailsSerializer
from .auth import (
    LoginCodeRequestSerializer,
    LoginCodeVerifySerializer,
    RegisterResendCodeSerializer,
    RegisterVerifyCodeSerializer,
    UnifiedEmailAuthRequestSerializer,
    UnifiedEmailAuthVerifySerializer,
)
from .passwords import (
    ChangePasswordCodeConfirmSerializer,
    ChangePasswordCodeRequestSerializer,
    ChangePasswordCodeVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
)

__all__ = [
    "AccountEmailsSerializer",
    "ChangePasswordCodeConfirmSerializer",
    "ChangePasswordCodeRequestSerializer",
    "ChangePasswordCodeVerifySerializer",
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
