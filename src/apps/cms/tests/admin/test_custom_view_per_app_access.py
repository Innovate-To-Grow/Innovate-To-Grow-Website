"""Regression tests: custom CMS admin views enforce per-app access.

Custom admin URLs registered via ``admin_site.admin_view`` are gated ONLY by
is_staff/is_active — Django does NOT run the per-app permission model for them.
Without an explicit re-check, a staff member whose ``Member.admin_apps`` lacks the
cms app could still hit these URLs and read CMS content / page-view PII or trigger
privileged import/upload actions.

These tests assert that, for a representative subset of every ``admin_view``-wrapped
view in the cms app, a staff member WITHOUT cms access gets HTTP 403 (Django renders
the view's ``PermissionDenied`` as a 403 under the test client), while a cms-granted
staff member or a superuser is allowed through (not 403).
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser


class CMSCustomViewPerAppAccessTests(TestCase):
    """Each ``admin_view``-wrapped custom view in the cms app re-checks cms access."""

    def setUp(self):
        cache.clear()
        # Staff member granted a DIFFERENT app (not cms): the escalation target.
        self.other_staff = make_admin(apps=["event"], email="event-only@example.com")
        # Staff member with cms access: must be allowed through.
        self.cms_staff = make_admin(apps=["cms"], email="cms-editor@example.com")
        # I2G Master: bypasses the per-app list entirely.
        self.master = make_superuser(email="cms-master@example.com")

    def tearDown(self):
        cache.clear()

    # --- helpers ---------------------------------------------------------

    def _assert_denied_for_other_app(self, url, *, method="get", **kwargs):
        self.client.force_login(self.other_staff)
        resp = getattr(self.client, method)(url, **kwargs)
        self.assertEqual(
            resp.status_code,
            403,
            f"{method.upper()} {url} should 403 for staff without cms access, got {resp.status_code}",
        )

    def _assert_allowed_for(self, user, url, *, method="get", **kwargs):
        self.client.force_login(user)
        resp = getattr(self.client, method)(url, **kwargs)
        self.assertNotEqual(
            resp.status_code,
            403,
            f"{method.upper()} {url} should NOT 403 for {user}, got 403",
        )

    # --- CMSPageAdmin custom views ---------------------------------------

    def test_cmspage_route_conflict_view(self):
        url = reverse("admin:cms_cmspage_route_conflict")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)
        self._assert_allowed_for(self.master, url)

    def test_cmspage_assets_list_view(self):
        url = reverse("admin:cms_cmspage_assets")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)

    def test_cmspage_assets_upload_view_post(self):
        url = reverse("admin:cms_cmspage_asset_upload")
        # POST (mutating) must also be guarded before any side effect.
        self._assert_denied_for_other_app(url, method="post", data={})
        self._assert_allowed_for(self.cms_staff, url, method="post", data={})

    def test_cmspage_preview_store_view_post(self):
        url = reverse("admin:cms_cmspage_preview")
        self._assert_denied_for_other_app(url, method="post", data="{}", content_type="application/json")
        self._assert_allowed_for(self.cms_staff, url, method="post", data="{}", content_type="application/json")

    def test_cmspage_export_all_view(self):
        url = reverse("admin:cms_cmspage_export")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)

    def test_cmspage_import_view(self):
        url = reverse("admin:cms_cmspage_import")
        # GET renders the import form; POST performs the import — both guarded.
        self._assert_denied_for_other_app(url)
        self._assert_denied_for_other_app(url, method="post", data={})
        self._assert_allowed_for(self.cms_staff, url)

    # --- StyleSheetAdmin custom views ------------------------------------

    def test_stylesheet_export_all_view(self):
        url = reverse("admin:cms_stylesheet_export")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)

    def test_stylesheet_import_view(self):
        url = reverse("admin:cms_stylesheet_import")
        self._assert_denied_for_other_app(url)
        self._assert_denied_for_other_app(url, method="post", data={})
        self._assert_allowed_for(self.cms_staff, url)

    # --- CMSEmbedWidgetAdmin custom views --------------------------------

    def test_embed_widget_app_routes_view(self):
        url = reverse("admin:cms_cmsembedwidget_app_routes")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)

    def test_embed_widget_page_blocks_view(self):
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)

    def test_embed_widget_page_info_view(self):
        url = reverse("admin:cms_cmsembedwidget_page_info")
        self._assert_denied_for_other_app(url)
        self._assert_allowed_for(self.cms_staff, url)

    # --- Page-view analytics module-level view ---------------------------

    def test_pageview_ip_geo_lookup_view(self):
        # Module-level function guarded via user_can_access_app(request.user, "cms").
        url = reverse("admin:cms_pageview_ip_geo_lookup")
        self._assert_denied_for_other_app(url, data={"ip": "8.8.8.8"})
        # A cms-granted member passes the access gate (invalid/empty IP still
        # returns a non-403 status, proving the guard let the request through).
        self._assert_allowed_for(self.cms_staff, url, data={"ip": ""})
        self._assert_allowed_for(self.master, url, data={"ip": ""})
