"""
URL configuration for authn app.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AccountEmailsView,
    ChangePasswordCodeConfirmView,
    ChangePasswordCodeRequestView,
    ChangePasswordCodeVerifyView,
    ChangePasswordView,
    ContactEmailDetailView,
    ContactEmailListCreateView,
    ContactEmailRequestVerificationView,
    ContactEmailVerifyCodeView,
    LoginCodeRequestView,
    LoginCodeVerifyView,
    LoginView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    ProfileView,
    PublicKeyView,
    RegisterResendCodeView,
    RegisterVerifyCodeView,
    RegisterView,
)

app_name = "authn"

urlpatterns = [
    # Public key for RSA encryption
    path("public-key/", PublicKeyView.as_view(), name="public-key"),
    # Registration
    path("register/", RegisterView.as_view(), name="register"),
    path("register/verify-code/", RegisterVerifyCodeView.as_view(), name="register-verify-code"),
    path("register/resend-code/", RegisterResendCodeView.as_view(), name="register-resend-code"),
    # Login
    path("login/", LoginView.as_view(), name="login"),
    path("login/request-code/", LoginCodeRequestView.as_view(), name="login-request-code"),
    path("login/verify-code/", LoginCodeVerifyView.as_view(), name="login-verify-code"),
    # Token refresh
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Password reset
    path("password-reset/request-code/", PasswordResetRequestView.as_view(), name="password-reset-request-code"),
    path("password-reset/verify-code/", PasswordResetVerifyView.as_view(), name="password-reset-verify-code"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    # Profile
    path("profile/", ProfileView.as_view(), name="profile"),
    path("account-emails/", AccountEmailsView.as_view(), name="account-emails"),
    # Change password
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("change-password/request-code/", ChangePasswordCodeRequestView.as_view(), name="change-password-request-code"),
    path("change-password/verify-code/", ChangePasswordCodeVerifyView.as_view(), name="change-password-verify-code"),
    path("change-password/confirm/", ChangePasswordCodeConfirmView.as_view(), name="change-password-confirm"),
    # Contact Emails (authenticated)
    path("contact-emails/", ContactEmailListCreateView.as_view(), name="contact-email-list-create"),
    path("contact-emails/<uuid:pk>/", ContactEmailDetailView.as_view(), name="contact-email-detail"),
    path(
        "contact-emails/<uuid:pk>/request-verification/",
        ContactEmailRequestVerificationView.as_view(),
        name="contact-email-request-verification",
    ),
    path(
        "contact-emails/<uuid:pk>/verify-code/",
        ContactEmailVerifyCodeView.as_view(),
        name="contact-email-verify-code",
    ),
]
