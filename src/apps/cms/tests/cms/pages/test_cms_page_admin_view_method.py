import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.models import CMSPage
from apps.cms.tests.cms.import_export.test_cms_import_export_extra import Member


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CMSPageAdminViewMethodTests(TestCase):
    def setUp(self):
        self.staff = Member.objects.create_superuser(password="testpass123", first_name="View", last_name="Admin")
        ContactEmail.objects.create(
            member=self.staff, email_address="view-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="view-admin@example.com", password="testpass123")

    def test_add_view_injects_editor_context(self):
        response = self.client.get(reverse("admin:cms_cmspage_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CMS_ROUTE_EDITOR")

    def test_save_related_persists_blocks_from_json(self):
        # Posting the add form with blocks_json drives save_related -> save_blocks_from_json.
        blocks_json = json.dumps(
            [{"block_type": "rich_text", "admin_label": "Body", "data": {"body_html": "<p>Hi</p>"}}]
        )
        response = self.client.post(
            reverse("admin:cms_cmspage_add"),
            {
                "slug": "save-related-page",
                "route": "/save-related-page",
                "title": "Save Related",
                "meta_description": "",
                "page_css_class": "",
                "status": "draft",
                "sort_order": 0,
                "published_at": "",
                "blocks_json": blocks_json,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        page = CMSPage.objects.get(slug="save-related-page")
        self.assertEqual(page.blocks.count(), 1)
        self.assertEqual(page.blocks.first().block_type, "rich_text")
