import json

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from cms.models import CMSBlock, CMSPage


class CMSExportActionTest(TestCase):
    """Tests for the batch action export (select pages -> action dropdown)."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            password="testpass123",
            first_name="Export",
            last_name="Admin",
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
            "/admin/cms/cmspage/",
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
            "/admin/cms/cmspage/",
            {"action": "export_pages", "_selected_action": [str(page.pk)]},
        )
        bundle = json.loads(response.content)
        self.assertEqual(len(bundle["pages"][0]["blocks"]), 1)


class CMSExportViewTest(TestCase):
    """Tests for the dedicated export view (toolbar button)."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            password="testpass123",
            first_name="Export",
            last_name="View",
        )
        self.client = APIClient()
        self.client.force_login(self.staff)

    def test_export_all_pages(self):
        CMSPage.objects.create(slug="page-1", route="/page-1", title="Page 1", status="published")
        CMSPage.objects.create(slug="page-2", route="/page-2", title="Page 2", status="draft")

        response = self.client.get("/admin/cms/cmspage/export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])

        bundle = json.loads(response.content)
        self.assertEqual(len(bundle["pages"]), 2)

    def test_export_filter_by_status(self):
        CMSPage.objects.create(slug="pub", route="/pub", title="Published", status="published")
        CMSPage.objects.create(slug="draft", route="/draft", title="Draft", status="draft")

        response = self.client.get("/admin/cms/cmspage/export/?status=published")
        bundle = json.loads(response.content)
        self.assertEqual(len(bundle["pages"]), 1)
        self.assertEqual(bundle["pages"][0]["slug"], "pub")

    def test_export_empty_returns_empty_list(self):
        response = self.client.get("/admin/cms/cmspage/export/")
        bundle = json.loads(response.content)
        self.assertEqual(bundle["pages"], [])

    def test_export_requires_staff(self):
        self.client.logout()
        response = self.client.get("/admin/cms/cmspage/export/")
        self.assertEqual(response.status_code, 302)  # redirect to login
