"""
URL configuration for authn app.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    LoginView,
    ProfileView,
    PublicKeyView,
    RegisterView,
    RequestLoginCodeView,
    ResendVerificationView,
    VerifyEmailCodeView,
    VerifyEmailView,
    VerifyLoginCodeView,
)

app_name = "authn"

urlpatterns = [
    # Public key for RSA encryption
    path("public-key/", PublicKeyView.as_view(), name="public-key"),
    # Registration
    path("register/", RegisterView.as_view(), name="register"),
    # Email verification
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("verify-email-code/", VerifyEmailCodeView.as_view(), name="verify-email-code"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
    # Login
    path("login/", LoginView.as_view(), name="login"),
    path("login/request-code/", RequestLoginCodeView.as_view(), name="login-request-code"),
    path("login/verify-code/", VerifyLoginCodeView.as_view(), name="login-verify-code"),
    # Token refresh
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Profile
    path("profile/", ProfileView.as_view(), name="profile"),
    # Change password
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
