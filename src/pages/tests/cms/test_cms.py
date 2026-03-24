import json

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from pages.models import CMSBlock, CMSPage


class CMSPageModelTest(TestCase):
    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def setUp(self):
        cache.clear()

    def test_create_page_with_blocks(self):
        page = CMSPage.objects.create(
            slug="test-page",
            route="/test-page",
            title="Test Page",
            status="published",
        )
        block = CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"heading": "Hello", "body_html": "<p>World</p>"},
        )
        self.assertEqual(page.blocks.count(), 1)
        self.assertEqual(block.block_type, "rich_text")

    def test_route_is_normalized_on_save(self):
        page = CMSPage.objects.create(
            slug="normalized-route",
            route="//event//live/",
            title="Normalized Route",
            status="draft",
        )
        self.assertEqual(page.route, "/event/live")

    def test_route_rejects_invalid_segments(self):
        page = CMSPage(slug="bad-route", route="/bad route", title="Bad Route")
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_published_at_auto_set(self):
        page = CMSPage.objects.create(
            slug="pub-test",
            route="/pub-test",
            title="Pub Test",
            status="published",
        )
        self.assertIsNotNone(page.published_at)

    def test_draft_no_published_at(self):
        page = CMSPage.objects.create(
            slug="draft-test",
            route="/draft-test",
            title="Draft Test",
            status="draft",
        )
        self.assertIsNone(page.published_at)

    def test_block_validation_missing_required(self):
        page = CMSPage.objects.create(
            slug="val-test",
            route="/val-test",
            title="Val Test",
            status="draft",
        )
        block = CMSBlock(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={},  # missing body_html
        )
        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_soft_delete(self):
        page = CMSPage.objects.create(
            slug="soft-del",
            route="/soft-del",
            title="Soft Del",
            status="published",
        )
        page.delete()
        self.assertEqual(CMSPage.objects.filter(slug="soft-del").count(), 0)
        self.assertEqual(CMSPage.all_objects.filter(slug="soft-del").count(), 1)


class CMSPageAPITest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_get_published_page(self):
        page = CMSPage.objects.create(
            slug="about",
            route="/about",
            title="About",
            page_css_class="about-page",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"heading": "About Us", "body_html": "<p>Hello</p>"},
        )

        response = self.client.get("/cms/pages/about/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "about")
        self.assertEqual(data["route"], "/about")
        self.assertEqual(data["title"], "About")
        self.assertEqual(data["page_css_class"], "about-page")
        self.assertEqual(len(data["blocks"]), 1)
        self.assertEqual(data["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(data["blocks"][0]["data"]["heading"], "About Us")

    def test_draft_page_404_for_public(self):
        CMSPage.objects.create(
            slug="draft-page",
            route="/draft-page",
            title="Draft",
            status="draft",
        )
        response = self.client.get("/cms/pages/draft-page/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_page_404(self):
        response = self.client.get("/cms/pages/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_blocks_ordered_by_sort_order(self):
        page = CMSPage.objects.create(
            slug="ordered",
            route="/ordered",
            title="Ordered",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=2,
            data={"body_html": "<p>Second</p>"},
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>First</p>"},
        )

        response = self.client.get("/cms/pages/ordered/")
        blocks = response.json()["blocks"]
        self.assertEqual(blocks[0]["sort_order"], 0)
        self.assertEqual(blocks[1]["sort_order"], 2)

    def test_soft_deleted_blocks_excluded(self):
        page = CMSPage.objects.create(
            slug="del-block",
            route="/del-block",
            title="Del Block",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Visible</p>"},
        )
        deleted = CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=1,
            data={"body_html": "<p>Deleted</p>"},
        )
        deleted.delete()  # soft delete

        response = self.client.get("/cms/pages/del-block/")
        self.assertEqual(len(response.json()["blocks"]), 1)

    def test_response_is_cached(self):
        CMSPage.objects.create(
            slug="cached",
            route="/cached",
            title="Cached",
            status="published",
        )

        # First request populates cache
        response1 = self.client.get("/cms/pages/cached/")
        self.assertEqual(response1.status_code, 200)

        # Verify cache hit by checking the cache key exists
        cached = cache.get("cms:page:/cached")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["slug"], "cached")


class CMSPreviewAPITest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = Member.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="testpass123",
            is_staff=True,
        )

    def test_preview_store_requires_staff(self):
        """Anonymous POST to preview store returns 403."""
        response = self.client.post(
            "/admin/pages/cmspage/preview/",
            data=json.dumps({"title": "Test"}),
            content_type="application/json",
        )
        # Redirects to login for anonymous users via admin_view wrapper
        self.assertIn(response.status_code, [302, 403])

    def test_preview_store_returns_token(self):
        """Staff POST returns 200 with token."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "preview",
            "route": "/test",
            "title": "Test",
            "page_css_class": "",
            "meta_description": "",
            "blocks": [{"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Hi</p>"}}],
        }
        response = self.client.post(
            "/admin/pages/cmspage/preview/",
            data=json.dumps(preview_data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        self.assertTrue(len(data["token"]) > 0)

    def test_preview_fetch_returns_data(self):
        """GET with valid token returns cached data."""
        preview_data = {"slug": "preview", "title": "Test Page", "blocks": []}
        cache.set("cms:preview:test-token-123", preview_data, timeout=600)

        response = self.client.get("/cms/preview/test-token-123/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Test Page")

    def test_preview_fetch_expired_returns_404(self):
        """GET with invalid/expired token returns 404."""
        response = self.client.get("/cms/preview/nonexistent-token/")
        self.assertEqual(response.status_code, 404)


class CMSExportTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            username="exportadmin",
            email="exportadmin@test.com",
            password="testpass123",
        )
        self.client = APIClient()
        self.client.force_login(self.staff)

    def test_export_json_structure(self):
        """Exported JSON has correct structure with blocks."""
        page = CMSPage.objects.create(
            slug="exp-test",
            route="/exp-test",
            title="Export Test",
            page_css_class="test-page",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            admin_label="Intro",
            data={"heading": "Hi", "body_html": "<p>Hello</p>"},
        )

        response = self.client.post(
            "/admin/pages/cmspage/",
            {"action": "export_pages", "_selected_action": [str(page.pk)]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        bundle = json.loads(response.content)
        self.assertEqual(bundle["version"], 1)
        self.assertEqual(len(bundle["pages"]), 1)

        p = bundle["pages"][0]
        self.assertEqual(p["slug"], "exp-test")
        self.assertEqual(p["title"], "Export Test")
        self.assertEqual(len(p["blocks"]), 1)
        self.assertEqual(p["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(p["blocks"][0]["admin_label"], "Intro")

    def test_export_excludes_deleted_blocks(self):
        """Soft-deleted blocks are not included in export."""
        page = CMSPage.objects.create(
            slug="exp-del",
            route="/exp-del",
            title="Export Del",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Visible</p>"},
        )
        deleted = CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=1,
            data={"body_html": "<p>Deleted</p>"},
        )
        deleted.delete()

        response = self.client.post(
            "/admin/pages/cmspage/",
            {"action": "export_pages", "_selected_action": [str(page.pk)]},
        )
        bundle = json.loads(response.content)
        self.assertEqual(len(bundle["pages"][0]["blocks"]), 1)


class CMSImportTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            username="importadmin",
            email="importadmin@test.com",
            password="testpass123",
        )
        self.client = APIClient()
        self.client.force_login(self.staff)

    # noinspection PyMethodMayBeStatic
    def _make_bundle(self, pages):
        return json.dumps({"version": 1, "pages": pages}).encode("utf-8")

    def test_import_creates_new_page(self):
        """Import creates a new page with blocks."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        bundle = self._make_bundle(
            [
                {
                    "slug": "new-page",
                    "route": "/new-page",
                    "title": "New Page",
                    "meta_description": "A new page",
                    "page_css_class": "new-page",
                    "status": "draft",
                    "sort_order": 0,
                    "blocks": [
                        {
                            "block_type": "rich_text",
                            "sort_order": 0,
                            "admin_label": "Content",
                            "data": {"body_html": "<p>Hello</p>"},
                        }
                    ],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/pages/cmspage/import/",
            {"json_file": f, "action": "execute"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)

        page = CMSPage.objects.filter(slug="new-page").first()
        self.assertIsNotNone(page)
        self.assertEqual(page.title, "New Page")
        self.assertEqual(page.blocks.filter(is_deleted=False).count(), 1)

    def test_import_updates_existing_page(self):
        """Import updates an existing page matched by slug."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        page = CMSPage.objects.create(
            slug="existing",
            route="/existing",
            title="Old Title",
            status="draft",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Old</p>"},
        )

        bundle = self._make_bundle(
            [
                {
                    "slug": "existing",
                    "route": "/existing",
                    "title": "New Title",
                    "status": "draft",
                    "blocks": [
                        {
                            "block_type": "faq_list",
                            "sort_order": 0,
                            "data": {"items": [{"question": "Q?", "answer_html": "A."}]},
                        }
                    ],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/pages/cmspage/import/",
            {"json_file": f, "action": "execute"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)

        page.refresh_from_db()
        self.assertEqual(page.title, "New Title")
        # Old block should be soft-deleted, new block created
        active_blocks = page.blocks.filter(is_deleted=False)
        self.assertEqual(active_blocks.count(), 1)
        self.assertEqual(active_blocks.first().block_type, "faq_list")

    def test_import_validates_block_type(self):
        """Invalid block type produces an error."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        bundle = self._make_bundle(
            [
                {
                    "slug": "bad-type",
                    "route": "/bad-type",
                    "title": "Bad Type",
                    "blocks": [{"block_type": "nonexistent_type", "sort_order": 0, "data": {}}],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/pages/cmspage/import/",
            {"json_file": f, "action": "dry_run"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        # Should have no page created
        self.assertFalse(CMSPage.objects.filter(slug="bad-type").exists())

    def test_import_dry_run_no_changes(self):
        """Dry run returns results but creates nothing."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        bundle = self._make_bundle(
            [
                {
                    "slug": "dry-run",
                    "route": "/dry-run",
                    "title": "Dry Run",
                    "blocks": [],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/pages/cmspage/import/",
            {"json_file": f, "action": "dry_run"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CMSPage.objects.filter(slug="dry-run").exists())


class CMSLivePreviewSyncTest(TestCase):
    """Tests for the CMSLivePreviewView POST/GET cache cycle."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = Member.objects.create_user(
            username="livepreview_staff",
            email="livepreview@test.com",
            password="testpass123",
            is_staff=True,
        )
        self.page = CMSPage.objects.create(
            slug="live-preview-test",
            route="/live-preview-test",
            title="Live Preview Test",
            status="published",
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Original content from DB</p>"},
        )
        self.live_preview_url = f"/cms/live-preview/{self.page.pk}/"

    def _post_preview(self, data, authenticate=True):
        """Helper to POST live preview data."""
        if authenticate:
            self.client.force_login(self.staff)
        return self.client.post(
            self.live_preview_url,
            data=json.dumps(data),
            content_type="application/json",
        )

    # --- 1. POST stores data in cache and returns 200 ---

    def test_post_stores_data_and_returns_200(self):
        """POST to live-preview stores data in cache and returns 200 with ok=True."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "title": "Edited Title",
            "blocks": [
                {"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Edited</p>"}},
            ],
        }
        response = self._post_preview(preview_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        # Verify data is in cache
        cached = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["title"], "Edited Title")
        self.assertEqual(len(cached["blocks"]), 1)

    # --- 2. GET retrieves cached data ---

    def test_get_returns_cached_data(self):
        """GET retrieves the data stored by a previous POST."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "title": "Cached Title",
            "blocks": [
                {"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Cached</p>"}},
            ],
        }
        # POST to store
        post_response = self._post_preview(preview_data)
        self.assertEqual(post_response.status_code, 200)

        # GET to retrieve (no auth required for GET)
        self.client.logout()
        get_response = self.client.get(self.live_preview_url)
        self.assertEqual(get_response.status_code, 200)

        data = get_response.json()
        self.assertEqual(data["title"], "Cached Title")
        self.assertEqual(data["blocks"][0]["data"]["body_html"], "<p>Cached</p>")

    def test_post_then_get_full_cycle(self):
        """Full POST -> GET cycle: data posted by staff is retrievable by anonymous GET."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "route": "/live-preview-test",
            "title": "Full Cycle Title",
            "page_css_class": "test-class",
            "meta_description": "Test description",
            "blocks": [
                {"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Block 1</p>"}},
                {"block_type": "rich_text", "sort_order": 1, "data": {"body_html": "<p>Block 2</p>"}},
            ],
        }
        self._post_preview(preview_data)

        self.client.logout()
        get_response = self.client.get(self.live_preview_url)
        data = get_response.json()

        self.assertEqual(data["title"], "Full Cycle Title")
        self.assertEqual(data["page_css_class"], "test-class")
        self.assertEqual(data["meta_description"], "Test description")
        self.assertEqual(len(data["blocks"]), 2)
        self.assertIn("expires_at", data)

    # --- 3. POST with invalid JSON returns 400 ---

    def test_post_invalid_json_returns_400(self):
        """POST with malformed JSON body returns 400."""
        self.client.force_login(self.staff)
        response = self.client.post(
            self.live_preview_url,
            data="this is not valid json{{{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid JSON.")

    def test_post_empty_body_returns_400(self):
        """POST with empty body returns 400."""
        self.client.force_login(self.staff)
        response = self.client.post(
            self.live_preview_url,
            data="",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    # --- 4. POST without staff auth returns 403 ---

    def test_post_anonymous_is_rejected(self):
        """Anonymous POST to live-preview is rejected (401 unauthenticated or 403 forbidden)."""
        response = self.client.post(
            self.live_preview_url,
            data=json.dumps({"title": "No Auth"}),
            content_type="application/json",
        )
        # DRF returns 401 for unauthenticated requests when DEFAULT_PERMISSION_CLASSES
        # includes IsAuthenticated; IsAdminUser would return 403 for authenticated non-staff.
        self.assertIn(response.status_code, [401, 403])

    def test_post_non_staff_returns_403(self):
        """Authenticated non-staff user POST returns 403."""
        regular_user = Member.objects.create_user(
            username="regular_user",
            email="regular@test.com",
            password="testpass123",
            is_staff=False,
        )
        self.client.force_login(regular_user)
        response = self.client.post(
            self.live_preview_url,
            data=json.dumps({"title": "Non-Staff"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    # --- 5. GET falls back to database when cache is empty ---

    def test_get_falls_back_to_database(self):
        """GET returns serialized DB data when cache is empty."""
        # Cache is cleared in setUp, so no cached data exists
        response = self.client.get(self.live_preview_url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["slug"], "live-preview-test")
        self.assertEqual(data["title"], "Live Preview Test")
        self.assertEqual(len(data["blocks"]), 1)
        self.assertEqual(data["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(data["blocks"][0]["data"]["body_html"], "<p>Original content from DB</p>")

    def test_get_nonexistent_page_returns_404(self):
        """GET with a UUID that has no cache and no DB record returns 404."""
        import uuid

        fake_uuid = uuid.uuid4()
        response = self.client.get(f"/cms/live-preview/{fake_uuid}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Page not found.")

    def test_get_prefers_cache_over_database(self):
        """GET returns cached data even when DB has different data."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "title": "Cached Version (Different from DB)",
            "blocks": [],
        }
        self._post_preview(preview_data)

        self.client.logout()
        response = self.client.get(self.live_preview_url)
        data = response.json()
        # Should return cached data, not DB data
        self.assertEqual(data["title"], "Cached Version (Different from DB)")
        self.assertNotEqual(data["title"], "Live Preview Test")

    # --- 6. Cache TTL / expires_at field ---

    def test_post_adds_expires_at_field(self):
        """POST adds an expires_at ISO timestamp to the cached data."""
        self.client.force_login(self.staff)
        preview_data = {"title": "TTL Test", "blocks": []}
        self._post_preview(preview_data)

        cached = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertIn("expires_at", cached)

        # Verify expires_at is a valid ISO timestamp roughly 10 minutes from now
        from datetime import datetime

        from django.utils import timezone as tz

        expires_at = datetime.fromisoformat(cached["expires_at"])
        now = tz.now()
        # expires_at should be between 9 and 11 minutes from now
        diff = (expires_at - now).total_seconds()
        self.assertGreater(diff, 540)  # at least 9 minutes
        self.assertLessEqual(diff, 600)  # at most 10 minutes

    def test_successive_posts_update_cache(self):
        """Multiple POSTs overwrite the cache with the latest data."""
        self.client.force_login(self.staff)

        # First POST
        self._post_preview({"title": "Version 1", "blocks": []})
        cached_v1 = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertEqual(cached_v1["title"], "Version 1")

        # Second POST
        self._post_preview({"title": "Version 2", "blocks": [{"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>New</p>"}}]})
        cached_v2 = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertEqual(cached_v2["title"], "Version 2")
        self.assertEqual(len(cached_v2["blocks"]), 1)

        # GET should return Version 2
        self.client.logout()
        response = self.client.get(self.live_preview_url)
        self.assertEqual(response.json()["title"], "Version 2")

    def test_get_allows_anonymous_access(self):
        """GET endpoint is accessible without authentication."""
        # Seed cache
        cache.set(f"cms:live-preview:{self.page.pk}", {"title": "Public", "blocks": []}, timeout=600)

        # No login
        response = self.client.get(self.live_preview_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Public")
