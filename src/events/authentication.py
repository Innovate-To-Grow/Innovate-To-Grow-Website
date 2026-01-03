"""
API Key authentication for Events sync endpoint.

Checks X-API-Key header against EVENTS_API_KEY setting.
"""

from django.conf import settings
from rest_framework import authentication, exceptions, permissions


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Simple API Key authentication via X-API-Key header.

    Requires EVENTS_API_KEY to be set in Django settings.
    """

    def authenticate(self, request):
        """Authenticate request using X-API-Key header."""

        api_key = request.META.get("HTTP_X_API_KEY") or request.META.get("X-API-Key")

        if not api_key:
            return None

        expected_key = getattr(settings, "EVENTS_API_KEY", None)

        if not expected_key:
            raise exceptions.AuthenticationFailed("EVENTS_API_KEY not configured on server.")

        if api_key != expected_key:
            raise exceptions.AuthenticationFailed("Invalid API key.")

        # Return a tuple of (user, token) - we don't need a user, so return None
        # Return the API key as the token so permission can check request.auth
        return (None, api_key)

    def authenticate_header(self, request):
        """Return a string to be used as the value of the `WWW-Authenticate` header."""
        return "ApiKey"


class APIKeyPermission(permissions.BasePermission):
    """
    Permission class that requires API Key authentication.

    Use with APIKeyAuthentication in DRF view.
    """

    def has_permission(self, request, view):
        """Check if request has valid API key."""
        # If authentication succeeded, request.auth will contain the API key
        return request.auth is not None
