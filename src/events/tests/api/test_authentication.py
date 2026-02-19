"""
Authentication tests for events app.
"""

from django.http import HttpRequest
from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed

from ...authentication import APIKeyAuthentication, APIKeyPermission


class APIKeyAuthenticationTest(TestCase):
    """Test APIKeyAuthentication."""

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_authenticates_with_valid_x_api_key_header(self):
        """Test authenticates with valid X-API-Key header."""
        auth = APIKeyAuthentication()
        request = HttpRequest()
        request.META["HTTP_X_API_KEY"] = "test-api-key-123"

        result = auth.authenticate(request)
        self.assertIsNotNone(result)
        self.assertIsNone(result[0])  # user is None
        self.assertEqual(result[1], "test-api-key-123")  # token is the API key

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_authenticates_with_x_api_key_in_meta(self):
        """Test authenticates with X-API-Key in META (HTTP_X_API_KEY)."""
        auth = APIKeyAuthentication()
        request = HttpRequest()
        request.META["X-API-Key"] = "test-api-key-123"

        result = auth.authenticate(request)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], "test-api-key-123")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_returns_none_when_no_api_key_provided(self):
        """Test returns None when no API key provided."""
        auth = APIKeyAuthentication()
        request = HttpRequest()
        # No API key in META

        result = auth.authenticate(request)
        self.assertIsNone(result)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_raises_authentication_failed_when_api_key_invalid(self):
        """Test raises AuthenticationFailed when API key invalid."""
        auth = APIKeyAuthentication()
        request = HttpRequest()
        request.META["HTTP_X_API_KEY"] = "wrong-key"

        with self.assertRaises(AuthenticationFailed) as context:
            auth.authenticate(request)
        self.assertIn("Invalid API key", str(context.exception))

    @override_settings(EVENTS_API_KEY="")
    def test_raises_authentication_failed_when_events_api_key_not_configured(self):
        """Test raises AuthenticationFailed when EVENTS_API_KEY not configured."""
        auth = APIKeyAuthentication()
        request = HttpRequest()
        request.META["HTTP_X_API_KEY"] = "any-key"

        with self.assertRaises(AuthenticationFailed) as context:
            auth.authenticate(request)
        self.assertIn("EVENTS_API_KEY not configured", str(context.exception))

    def test_authenticate_header_returns_apikey(self):
        """Test authenticate_header returns 'ApiKey'."""
        auth = APIKeyAuthentication()
        request = HttpRequest()
        header = auth.authenticate_header(request)
        self.assertEqual(header, "ApiKey")


class APIKeyPermissionTest(TestCase):
    """Test APIKeyPermission."""

    def test_grants_permission_when_request_auth_is_set(self):
        """Test grants permission when request.auth is set (authentication succeeded)."""
        permission = APIKeyPermission()

        # Mock request with auth set
        class MockRequest:
            def __init__(self):
                self.auth = "test-api-key"

        request = MockRequest()
        result = permission.has_permission(request, None)
        self.assertTrue(result)

    def test_denies_permission_when_request_auth_is_none(self):
        """Test denies permission when request.auth is None (authentication failed)."""
        permission = APIKeyPermission()

        # Mock request without auth
        class MockRequest:
            def __init__(self):
                self.auth = None

        request = MockRequest()
        result = permission.has_permission(request, None)
        self.assertFalse(result)
