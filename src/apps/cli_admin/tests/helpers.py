import base64
import hashlib

from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.cli_admin.models import CliAccessToken, CliAuthorizationCode
from apps.event.tests.helpers import make_member, make_superuser  # noqa: F401 (re-exported for tests)

VALID_REDIRECT_URI = "http://127.0.0.1:54321/callback"


def challenge_for(verifier):
    """Compute the S256 code_challenge for a verifier (must match pkce.verify_pkce_s256)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def make_staff(email="staff@example.com", **kwargs):
    return make_member(email=email, is_staff=True, **kwargs)


def issue_token(member, **kwargs):
    """Create a CliAccessToken; returns (token, raw_token)."""
    raw = CliAccessToken.generate_raw_token()
    token = CliAccessToken.objects.create(token_hash=CliAccessToken.hash_token(raw), member=member, **kwargs)
    return token, raw


def issue_code(member, *, challenge, redirect_uri=VALID_REDIRECT_URI, **kwargs):
    """Create a CliAuthorizationCode; returns (code, raw_code)."""
    raw = CliAuthorizationCode.generate_raw_code()
    code = CliAuthorizationCode.objects.create(
        code_hash=CliAuthorizationCode.hash_code(raw),
        member=member,
        code_challenge=challenge,
        redirect_uri=redirect_uri,
        **kwargs,
    )
    return code, raw


class CliApiTestCase(APITestCase):
    """Base API test case that resets the throttle cache between tests."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def auth(self, raw_token):
        return {"HTTP_AUTHORIZATION": f"Bearer {raw_token}"}
