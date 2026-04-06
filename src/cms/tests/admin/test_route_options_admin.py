import json

from django.test import TestCase

from cms.admin.layout.route_options import build_route_editor_context
from cms.models import CMSPage


class RouteOptionsAdminTests(TestCase):
    def test_menu_admin_prefers_app_routes_when_url_exists_in_both_sources(self):
        CMSPage.objects.create(
            slug="news-page",
            route="/news",
            title="News CMS Duplicate",
            status="published",
        )

        context = build_route_editor_context()
        app_routes = json.loads(context["app_routes_json"])
        cms_routes = json.loads(context["cms_routes_json"])

        self.assertTrue(any(route["url"] == "/news" for route in app_routes))
        self.assertFalse(any(route["url"] == "/news" for route in cms_routes))

    def test_footer_admin_prefers_app_routes_when_url_exists_in_both_sources(self):
        CMSPage.objects.create(
            slug="subscribe-page",
            route="/subscribe",
            title="Subscribe CMS Duplicate",
            status="published",
        )

        context = build_route_editor_context()
        app_routes = json.loads(context["app_routes_json"])
        cms_routes = json.loads(context["cms_routes_json"])

        self.assertTrue(any(route["url"] == "/subscribe" for route in app_routes))
        self.assertFalse(any(route["url"] == "/subscribe" for route in cms_routes))
