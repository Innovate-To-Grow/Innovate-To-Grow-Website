"""Bearer headers for a session the SPA may still hold but the API no longer honours.

The shared axios client attaches whatever access token local storage holds to every request. A view that
still runs a strict ``JWTAuthentication`` answers 401 to each header below before its handler ever runs,
even when the view is ``AllowAny``.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authn.models import Member


def valid_bearer_header(member) -> str:
    """``Authorization`` value carrying a currently valid access token for ``member``."""
    return f"Bearer {RefreshToken.for_user(member).access_token}"


def stale_bearer_headers() -> dict[str, str]:
    """``Authorization`` values that authenticate as nobody, keyed by why."""
    expired_owner = Member.objects.create_user(password="StrongPass123!", is_active=True)
    expired = RefreshToken.for_user(expired_owner).access_token
    expired.set_exp(from_time=timezone.now() - timedelta(hours=2))  # one-hour lifetime: expired an hour ago

    deleted = Member.objects.create_user(password="StrongPass123!", is_active=True)
    deleted_header = valid_bearer_header(deleted)
    deleted.delete()

    inactive = Member.objects.create_user(password="StrongPass123!", is_active=False)

    live = Member.objects.create_user(password="StrongPass123!", is_active=True)
    refresh_as_access = str(RefreshToken.for_user(live))

    valid = str(RefreshToken.for_user(live).access_token)
    header, payload, signature = valid.split(".")
    flipped = "A" if signature[0] != "A" else "B"
    tampered = ".".join((header, payload, flipped + signature[1:]))

    return {
        "expired access token": f"Bearer {expired}",
        "garbage token": "Bearer not-a-jwt",
        "empty token": "Bearer ",
        "too many parts": "Bearer a b",
        "tampered signature": f"Bearer {tampered}",
        "refresh token in place of access": f"Bearer {refresh_as_access}",
        "deleted member": deleted_header,
        "inactive member": valid_bearer_header(inactive),
    }


def assert_stale_bearer_reads_as_anonymous(test, send, *, project=None) -> None:
    """Each stale header must get exactly the response an anonymous caller gets.

    ``send(**extra)`` issues the request under test with ``extra`` as request headers. The baseline is the
    same request without an ``Authorization`` header; it must not itself be a 401, or the comparison proves
    nothing. Bodies are compared byte for byte unless ``project(response)`` picks the part that is stable
    between two identical requests (a response that carries a fresh id, say).
    """
    project = project or (lambda response: response.content)
    baseline = send()
    test.assertNotEqual(baseline.status_code, 401, "the anonymous request itself 401s")
    for label, header in stale_bearer_headers().items():
        with test.subTest(stale=label):
            response = send(HTTP_AUTHORIZATION=header)
            test.assertEqual(response.status_code, baseline.status_code, response.content[:200])
            test.assertEqual(project(response), project(baseline))
