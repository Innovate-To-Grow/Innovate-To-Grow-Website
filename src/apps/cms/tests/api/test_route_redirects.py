"""Public CMS page API redirect behavior."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import CMSPage, RouteRedirect


class CMSRouteRedirectAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.target = CMSPage.objects.create(
            slug="new-page",
            route="/new-page",
            title="New Page",
            status="published",
        )

    def tearDown(self):
        cache.clear()

    def test_active_redirect_returns_permanent_mapping(self):
        RouteRedirect.objects.create(
            source_path="/Old-Page",
            destination_path=self.target.route,
            is_active=True,
        )

        response = self.client.get("/cms/pages/Old-Page/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"redirect_to": "/new-page", "permanent": True})
        self.assertEqual(cache.get("cms:page:/Old-Page"), response.json())

    def test_active_redirect_supports_legacy_punctuation(self):
        RouteRedirect.objects.create(
            source_path="/Archive.v1/~old+page",
            destination_path=self.target.route,
            is_active=True,
        )

        response = self.client.get("/cms/pages/Archive.v1/~old+page/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"redirect_to": "/new-page", "permanent": True})

    def test_inactive_redirect_is_not_returned(self):
        RouteRedirect.objects.create(
            source_path="/old-page",
            destination_path=self.target.route,
            is_active=False,
        )
        response = self.client.get("/cms/pages/old-page/")
        self.assertEqual(response.status_code, 404)

    def test_redirect_matching_is_case_sensitive(self):
        RouteRedirect.objects.create(
            source_path="/FAQs",
            destination_path=self.target.route,
            is_active=True,
        )
        self.assertEqual(self.client.get("/cms/pages/FAQs/").status_code, 200)
        self.assertEqual(self.client.get("/cms/pages/faqs/").status_code, 404)

    def test_preview_mode_bypasses_redirect(self):
        RouteRedirect.objects.create(
            source_path="/old-preview",
            destination_path=self.target.route,
            is_active=True,
        )
        response = self.client.get("/cms/pages/old-preview/?preview=true")
        self.assertEqual(response.status_code, 404)

    def test_trailing_slash_variant_resolves_same_mapping(self):
        RouteRedirect.objects.create(
            source_path="/legacy",
            destination_path=self.target.route,
            is_active=True,
        )
        response = self.client.get("/cms/pages/legacy//")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_to"], "/new-page")
