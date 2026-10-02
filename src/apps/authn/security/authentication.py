"""
Authentication classes for public endpoints that may optionally know who is calling.
"""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class SoftJWTAuthentication(JWTAuthentication):
    """``JWTAuthentication`` that reads a bad Bearer token as "anonymous" instead of answering 401.

    DRF authenticates *before* it checks permissions, so on a stock ``JWTAuthentication`` an expired, garbage,
    wrongly signed, deleted-member or inactive-member token 401s even a view that is ``AllowAny``. The SPA's
    shared axios client attaches whatever access token local storage holds to every request and, on a 401 it
    cannot refresh, clears the stored session, so one stale token would break unrelated public requests.

    Use this on a public endpoint that still has to honour a *valid* token (it reads ``request.user``, or a
    throttle such as ``AnonRateThrottle`` does). An endpoint that never reads the caller's identity sets
    ``authentication_classes = []`` instead. An endpoint that needs the token for authorization keeps the
    strict ``JWTAuthentication``: this class must never guard one, since it can only ever answer anonymous.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            # ``InvalidToken`` (bad, expired, wrong signature, wrong token type, wrong claims) and the
            # missing / inactive user failures are all ``AuthenticationFailed``. Anything else, such as a
            # database error, is a real fault and still propagates.
            return None
