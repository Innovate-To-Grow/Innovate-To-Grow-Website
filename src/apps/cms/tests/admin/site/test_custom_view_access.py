"""Access to the custom CMS admin views.

Every custom URL is wrapped in ``admin_site.admin_view``, so a regular member is redirected to the admin login before
the view runs. The ModelAdmin views also re-check their own permission hook (defence in depth), exercised here by
calling them directly with a non-Admin request. Every Admin is allowed through.
"""

from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.cms.models import CMSEmbedWidget, CMSPage
from apps.event.tests.helpers import make_admin, make_member

CUSTOM_URLS = [
    ("admin:cms_cmspage_route_conflict", "get", {}),
    ("admin:cms_cmspage_assets", "get", {}),
    ("admin:cms_cmspage_asset_upload", "post", {"data": {}}),
    ("admin:cms_cmspage_preview", "post", {"data": "{}", "content_type": "application/json"}),
    ("admin:cms_cmspage_export", "get", {}),
    ("admin:cms_cmspage_import", "get", {}),
    ("admin:cms_cmspage_import", "post", {"data": {}}),
    ("admin:cms_cmsembedwidget_app_routes", "get", {}),
    ("admin:cms_cmsembedwidget_page_blocks", "get", {}),
    ("admin:cms_cmsembedwidget_page_info", "get", {}),
    ("admin:cms_pageview_ip_geo_lookup", "get", {"data": {"ip": ""}}),
]


class CMSCustomViewAccessTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_a_regular_member_is_sent_to_the_login_on_every_custom_url(self):
        self.client.force_login(make_member(email="cms-member@example.com"))

        for name, method, kwargs in CUSTOM_URLS:
            with self.subTest(url=name, method=method):
                response = getattr(self.client, method)(reverse(name), **kwargs)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_every_admin_is_let_through(self):
        self.client.force_login(make_admin(email="cms-editor@example.com"))

        for name, method, kwargs in CUSTOM_URLS:
            with self.subTest(url=name, method=method):
                response = getattr(self.client, method)(reverse(name), **kwargs)
                self.assertNotEqual(response.status_code, 403, f"{method.upper()} {name}")
                self.assertNotIn("/login/", response.get("Location", ""), f"{method.upper()} {name}")

    def test_the_views_refuse_a_non_admin_even_when_called_directly(self):
        request = RequestFactory().get("/")
        request.user = make_member(email="cms-direct@example.com")
        page_admin = admin.site._registry[CMSPage]
        widget_admin = admin.site._registry[CMSEmbedWidget]
        views = [
            page_admin.preview_store_view,
            page_admin.route_conflict_view,
            page_admin.assets_list_view,
            page_admin.assets_upload_view,
            page_admin.export_all_view,
            page_admin.import_view,
            widget_admin.app_routes_view,
            widget_admin.page_blocks_view,
            widget_admin.page_info_view,
        ]
        for view in views:
            with self.subTest(view=view.__name__), self.assertRaises(PermissionDenied):
                view(request)
