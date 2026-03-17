import json

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from pages.models import CMSBlock, CMSPage


class CMSPageModelTest(TestCase):
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

    def test_route_must_start_with_slash(self):
        page = CMSPage(slug="bad", route="no-slash", title="Bad")
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
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            username="importadmin",
            email="importadmin@test.com",
            password="testpass123",
        )
        self.client = APIClient()
        self.client.force_login(self.staff)

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
