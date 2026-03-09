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
)

app_name = "authn"

urlpatterns = [
    # Public key for RSA encryption
    path("public-key/", PublicKeyView.as_view(), name="public-key"),
    # Registration
    path("register/", RegisterView.as_view(), name="register"),
    # Login
    path("login/", LoginView.as_view(), name="login"),
    # Token refresh
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Profile
    path("profile/", ProfileView.as_view(), name="profile"),
    # Change password
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
