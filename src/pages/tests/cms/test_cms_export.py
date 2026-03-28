import json

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from pages.models import CMSBlock, CMSPage


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
