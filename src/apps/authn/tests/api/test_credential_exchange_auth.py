"""Regression guard: credential-exchange views must never run JWT authentication.

These endpoints are authenticated by a one-time credential the request itself carries (an emailed token,
a refresh token). The SPA's shared axios client attaches whatever access token local storage holds to
every request, and DRF authenticates before it checks permissions, so a stale, expired or other-account
Bearer would 401 the request before the handler could consume the credential. Dropping
``authentication_classes = []`` from any of these views silently brings that failure back.
"""

from django.test import SimpleTestCase

from apps.authn.views import ImpersonateLoginView, LogoutView, PublicTokenRefreshView
from apps.mail.views import LoginLinkView, OneClickUnsubscribeView, ResubscribeView

CREDENTIAL_EXCHANGE_VIEWS = [
    LoginLinkView,
    ImpersonateLoginView,
    LogoutView,
    OneClickUnsubscribeView,
    ResubscribeView,
]


class CredentialExchangeAuthenticationTests(SimpleTestCase):
    def test_exchange_views_run_no_authentication(self):
        for view in CREDENTIAL_EXCHANGE_VIEWS:
            with self.subTest(view=view.__name__):
                self.assertEqual(view.authentication_classes, [])

    def test_token_refresh_view_runs_no_authentication(self):
        # SimpleJWT's TokenViewBase already opts out; pin it so a future override cannot regress it.
        self.assertFalse(PublicTokenRefreshView.authentication_classes)
