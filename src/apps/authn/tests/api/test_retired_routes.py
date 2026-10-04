"""Retired authn endpoints stay gone."""

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

RETIRED_PATHS = (
    "/authn/subscribe/",  # anonymous newsletter sign-up; the SPA's /subscribe page signs in by email code instead
    "/authn/unsubscribe-login/",  # exchange behind the old /unsubscribe-login#token=X email links
)


class RetiredAuthnRoutesTests(SimpleTestCase):
    def test_retired_paths_do_not_resolve(self):
        for path in RETIRED_PATHS:
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_retired_paths_return_404(self):
        for path in RETIRED_PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, {"token": "x"}).status_code, 404)
