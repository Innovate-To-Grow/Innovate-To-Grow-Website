"""Regression guard: a public API view must not run a strict ``JWTAuthentication``.

DRF authenticates before it checks permissions, so a strict ``JWTAuthentication`` on an ``AllowAny`` view 401s a
request whose Bearer token is expired, garbage, or for a deleted or inactive member. The SPA's shared axios client
attaches whatever access token local storage holds to every request, and clears the stored session when it cannot
refresh after a 401, so one stale token would break requests that never needed a login.

A public view either runs no authentication (``authentication_classes = []``) or, when it reads the caller,
``SoftJWTAuthentication``. A view that needs the token for authorization is not ``AllowAny`` and is out of scope.
"""

from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.authn.security import SoftJWTAuthentication

# Credential-exchange views (emailed login link, impersonation, one-click unsubscribe, logout) that the login-link
# fix moves to ``authentication_classes = []``. That change is not on this branch yet, so they are excused here. Once it
# lands, empty this set: ``test_the_excused_views_still_need_the_excuse`` fails until you do.
PENDING_CREDENTIAL_EXCHANGE_FIX = {
    "ImpersonateLoginView",
    "LoginLinkView",
    "LogoutView",
    "OneClickUnsubscribeView",
    "ResubscribeView",
    "UnsubscribeAutoLoginView",
}


def api_views(patterns, prefix=""):
    """Yield ``(route, view class)`` for every DRF view reachable from ``patterns``."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from api_views(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            view_class = getattr(pattern.callback, "cls", None)  # ``as_view()`` keeps the class on the function
            if isinstance(view_class, type) and issubclass(view_class, APIView):
                yield prefix + str(pattern.pattern), view_class


def is_public(view_class):
    return bool(view_class.permission_classes) and all(p is AllowAny for p in view_class.permission_classes)


def runs_strict_jwt(view_class):
    return any(
        issubclass(auth, JWTAuthentication) and not issubclass(auth, SoftJWTAuthentication)
        for auth in view_class.authentication_classes
    )


def strict_public_views():
    return sorted(
        (route, view_class)
        for route, view_class in api_views(get_resolver().url_patterns)
        if is_public(view_class) and runs_strict_jwt(view_class)
    )


class PublicEndpointAuthenticationTests(SimpleTestCase):
    def test_no_public_view_runs_strict_jwt_authentication(self):
        offenders = [
            f"{route} ({view_class.__name__})"
            for route, view_class in strict_public_views()
            if view_class.__name__ not in PENDING_CREDENTIAL_EXCHANGE_FIX
        ]

        self.assertEqual(offenders, [])

    def test_the_excused_views_still_need_the_excuse(self):
        still_strict = {view_class.__name__ for _, view_class in strict_public_views()}

        self.assertEqual(PENDING_CREDENTIAL_EXCHANGE_FIX & still_strict, PENDING_CREDENTIAL_EXCHANGE_FIX)

    def test_the_walk_finds_the_public_views_it_is_meant_to_guard(self):
        public = {
            view_class.__name__ for _, view_class in api_views(get_resolver().url_patterns) if is_public(view_class)
        }

        self.assertGreaterEqual(
            public,
            {
                "MaintenanceBypassView",
                "CMSPreviewFetchView",
                "LayoutAPIView",
                "NewsListAPIView",
                "PastProjectsAPIView",
                "CurrentEventScheduleView",
                "EventRegistrationOptionsView",
                "PageViewCreateView",
                "PublicAssistantChatView",
            },
        )
