import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from cms.admin.cms.cms_page import CMSPageAdminForm
from cms.models import CMSPage

Member = get_user_model()


class CMSPageAdminFormTests(TestCase):
    # noinspection PyMethodMayBeStatic
    def build_form_data(self, **overrides):
        data = {
            "slug": "cms-admin-test",
            "route": "/cms-admin-test/",
            "title": "CMS Admin Test",
            "meta_description": "",
            "page_css_class": "",
            "status": "draft",
            "sort_order": 0,
            "is_deleted": False,
            "deleted_at": "",
            "published_at": "",
        }
        data.update(overrides)
        return data

    def test_route_form_normalizes_trailing_slash(self):
        form = CMSPageAdminForm(data=self.build_form_data(route="/about/"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["route"], "/about")

    def test_route_form_rejects_conflict_after_normalization(self):
        CMSPage.objects.create(
            slug="existing-route",
            route="/event/live",
            title="Existing Route",
            status="published",
        )

        form = CMSPageAdminForm(
            data=self.build_form_data(
                slug="conflicting-route",
                route="//event//live/",
                title="Conflicting Route",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("route", form.errors)
        self.assertIn("already used", form.errors["route"][0])


class CMSPageAdminViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="testpass123",
        )
        self.client.login(username="admin", password="testpass123")

    def test_route_conflict_endpoint_reports_conflict(self):
        page = CMSPage.objects.create(
            slug="existing-homepage",
            route="/home-during-event",
            title="Existing Homepage",
            status="published",
        )

        response = self.client.get(
            reverse("admin:cms_cmspage_route_conflict"),
            {"route": "//home-during-event/", "page_id": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["normalized_route"], page.route)
        self.assertTrue(response.json()["has_conflict"])


class CMSPageChangeFormRenderTests(TestCase):
    """Tests that the CMS page change form renders correctly with editor JS config."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.admin_user = Member.objects.create_superuser(
            username="editor",
            email="editor@example.com",
            password="testpass123",
        )
        self.client.login(username="editor", password="testpass123")
        self.page = CMSPage.objects.create(
            slug="test-editor-page",
            route="/test-editor-page",
            title="Test Editor Page",
            status="draft",
        )

    def tearDown(self):
        cache.clear()

    def test_change_form_renders_for_staff_user(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_change_form_contains_route_editor_config_with_page_id(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn("CMS_ROUTE_EDITOR", content)
        self.assertIn(str(self.page.pk), content)

    def test_change_form_includes_block_editor_script(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn("cms-block-editor.js", content)

    def test_change_form_has_preview_button(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn("openLivePreview", content)
        self.assertIn("Preview", content)

    def test_preview_store_endpoint_returns_token(self):
        url = reverse("admin:cms_cmspage_preview")
        payload = {
            "title": "Preview Test",
            "route": "/preview-test",
            "blocks": [{"block_type": "rich_text", "data": {"body": "<p>Hello</p>"}}],
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        self.assertTrue(len(data["token"]) > 0)

        # Verify the preview data was stored in cache
        cached = cache.get(f"cms:preview:{data['token']}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["title"], "Preview Test")

    def test_preview_store_endpoint_rejects_get(self):
        url = reverse("admin:cms_cmspage_preview")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_preview_store_endpoint_rejects_invalid_json(self):
        url = reverse("admin:cms_cmspage_preview")
        response = self.client.post(
            url,
            data="not-valid-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
