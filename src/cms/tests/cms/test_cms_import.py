import json

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from cms.models import CMSBlock, CMSPage


class CMSImportTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            password="testpass123",
            first_name="Import",
            last_name="Admin",
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
            "/admin/cms/cmspage/import/",
            {"json_file": f, "action": "execute"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)

        page = CMSPage.objects.filter(slug="new-page").first()
        self.assertIsNotNone(page)
        self.assertEqual(page.title, "New Page")
        self.assertEqual(page.blocks.count(), 1)

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
            "/admin/cms/cmspage/import/",
            {"json_file": f, "action": "execute"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)

        page.refresh_from_db()
        self.assertEqual(page.title, "New Title")
        # Old block should be soft-deleted, new block created
        active_blocks = page.blocks
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
            "/admin/cms/cmspage/import/",
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
            "/admin/cms/cmspage/import/",
            {"json_file": f, "action": "dry_run"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CMSPage.objects.filter(slug="dry-run").exists())
